"""
Subagents & Delegation (Anthropic)

Demonstrates a parent agent that delegates through a spawn_subagent tool. Each child is a fresh
agent loop with its own message history: it works through a subtask, however many files that
takes, and hands back only a summary. The parent's context stays clean.

Limits on depth, fan-out, and total agents keep delegation from running away, and every child's
token usage rolls up into a single report.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.tree import Tree

from common import AnthropicTokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
PARENT_EFFORT = "medium"
# Children do narrow, well-scoped reading, so they use less effort instead of a different model
CHILD_EFFORT = "low"
MAX_ITERATIONS = 12

# Re-run a safety-declined turn on a fallback model instead of ending the loop
FALLBACK_BETA = "server-side-fallback-2026-07-01"

MAX_READ_CHARS = 6_000
MAX_SUMMARY_CHARS = 2_000

# Tools can only read inside the course's first module
EXPLORE_ROOT = (Path(__file__).parent / "../../01-foundations").resolve()

PARENT_SYSTEM_PROMPT = """You coordinate research on a codebase and write the final answer.

When a question spans more than one folder, don't read those files yourself: give each folder
its own spawn_subagent call, in one turn, so they run at the same time and the file contents stay
out of your context. A subagent knows only what you put in its task, so include the goal and the
paths to look at. Answer directly only when a single file settles the question. Synthesize the
summaries into a concise answer, and don't repeat them."""

CHILD_SYSTEM_PROMPT = f"""You are a research subagent. Complete the one subtask you were given.

Your final message is the only thing the coordinator will ever see, and your tool calls and
files stay behind. Report conclusions with the file paths that support them, under
{MAX_SUMMARY_CHARS} characters. If you could not finish, say what is missing."""

READ_TOOLS = [
    {
        "name": "list_files",
        "description": "List files and folders at a path relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Relative folder path"}},
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": (
            f"Read a text file, {MAX_READ_CHARS} characters at a time. If it's longer, the "
            "result says which offset to pass to read the next part."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "offset": {"type": "integer", "description": "Character to start from"},
            },
            "required": ["path"],
        },
    },
]

SPAWN_TOOL = {
    "name": "spawn_subagent",
    "description": (
        "Delegate a self-contained subtask to a new agent with its own context. Returns only "
        "its final summary. Use for work that needs reading several files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Full instructions; the subagent can't see this conversation",
            },
        },
        "required": ["task"],
    },
}


@dataclass(frozen=True)
class DelegationLimits:
    """Bounds on the agent tree, because each child costs real money."""

    max_depth: int = 2
    max_fan_out: int = 4
    max_total_agents: int = 8


@dataclass
class AgentNode:
    """One agent in the tree, with its token usage and last request size."""

    label: str
    tracker: AnthropicTokenTracker = field(default_factory=AnthropicTokenTracker)
    context_tokens: int = 0
    children: list["AgentNode"] = field(default_factory=list)

    def total_tokens(self) -> int:
        """Tokens used by this agent and everything below it."""
        own: int = self.tracker.get_total_tokens()
        return own + sum(c.total_tokens() for c in self.children)


class DelegationBudget:
    """Counts agents across the whole tree; children run on threads, so counting is locked."""

    def __init__(self, limits: DelegationLimits) -> None:
        self.limits = limits
        self.spawned = 0
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        """Reserve one agent from the total budget, or report that it has run out."""
        with self._lock:
            if self.spawned >= self.limits.max_total_agents:
                return False
            self.spawned += 1
            return True


def read_only_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Run a read-only tool, confined to the exploration root."""
    target = (EXPLORE_ROOT / tool_input.get("path", ".")).resolve()
    if not target.is_relative_to(EXPLORE_ROOT):
        raise ValueError(f"path {tool_input.get('path')!r} is outside the project")
    if name == "list_files":
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
        return "\n".join(e for e in entries if not e.startswith(".") and e != "__pycache__/")
    if name == "read_file":
        text = target.read_text()
        offset = int(tool_input.get("offset", 0))
        end = offset + MAX_READ_CHARS
        page = text[offset:end]
        # Say so when there's more: a silent cut leaves the agent unable to finish reading
        return (
            f"{page}\n... [{len(text) - end} more characters: use offset={end}]"
            if end < len(text)
            else page
        )
    raise ValueError(f"Unknown tool: {name}")


class Agent:
    """An agent loop that may delegate, as long as it's above the depth limit."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        budget: DelegationBudget,
        node: AgentNode,
        depth: int = 0,
    ) -> None:
        self.client = client
        self.budget = budget
        self.node = node
        self.depth = depth
        self.is_child = depth > 0
        # The last agent allowed never even sees the tool, which beats refusing its calls
        self.can_delegate = depth < budget.limits.max_depth
        self.tools = [*READ_TOOLS, SPAWN_TOOL] if self.can_delegate else READ_TOOLS

    def run(self, task: str) -> str:
        """Run the loop to completion with a brand-new message history."""
        # This list is the isolation: a child starts from its task, with none of the parent's turns
        messages: list[Any] = [{"role": "user", "content": task}]

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"[{self.node.label}] iteration {iteration + 1}")
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                output_config={"effort": CHILD_EFFORT if self.is_child else PARENT_EFFORT},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=CHILD_SYSTEM_PROMPT if self.is_child else PARENT_SYSTEM_PROMPT,
                tools=self.tools,
                messages=messages,
            )
            self.node.tracker.track(response.usage)
            self.node.context_tokens = response.usage.input_tokens
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                text = "\n".join(b.text for b in response.content if b.type == "text")
                return text or f"(no text returned, stop_reason={response.stop_reason})"

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            messages.append({"role": "user", "content": self.run_tool_round(tool_uses)})

        return "Incomplete: reached the iteration limit before finishing."

    def run_tool_round(self, tool_uses: list[Any]) -> list[dict[str, Any]]:
        """Execute one round of tool calls, running spawned subagents in parallel."""
        spawns = [b for b in tool_uses if b.name == "spawn_subagent"]
        accepted = spawns[: self.budget.limits.max_fan_out]
        results: dict[str, tuple[str, bool]] = {}

        # Refused calls still need a tool_result, or the API rejects the next request
        for block in spawns[self.budget.limits.max_fan_out :]:
            results[block.id] = (f"Refused: at most {len(accepted)} subagents per turn.", True)

        if accepted:
            with ThreadPoolExecutor(max_workers=len(accepted)) as pool:
                # Number children here, before threads start, so labels are stable and unique
                first = len(self.node.children) + 1
                futures = {
                    block.id: pool.submit(self.spawn, block.input.get("task", ""), number)
                    for number, block in enumerate(accepted, first)
                }
                results.update({block_id: f.result() for block_id, f in futures.items()})

        for block in tool_uses:
            if block.name != "spawn_subagent":
                logger.info(f"[{self.node.label}] 🔧 {block.name}({json.dumps(block.input)})")
                results[block.id] = self.run_read_tool(block.name, block.input)

        # Keep the original order, all in a single user message
        return [
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": results[block.id][0],
                "is_error": results[block.id][1],
            }
            for block in tool_uses
        ]

    @staticmethod
    def run_read_tool(name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Run a read tool, turning failures into errors the model can act on."""
        try:
            return read_only_tool(name, tool_input), False
        except (OSError, ValueError) as e:
            return f"Error: {e}", True

    def spawn(self, task: str, number: int) -> tuple[str, bool]:
        """Run a child agent to completion and return only its capped summary."""
        if not self.can_delegate:
            return "Refused: this agent is at the maximum delegation depth.", True
        if not self.budget.try_acquire():
            return "Refused: the budget for this task is used up. Finish with what you have.", True

        child_node = AgentNode(label=f"{self.node.label}.{number}")
        self.node.children.append(child_node)
        logger.info(f"🌱 Spawning {child_node.label}: {task[:80]}")

        try:
            summary = Agent(self.client, self.budget, child_node, self.depth + 1).run(task)
        except anthropic.APIError as e:
            # One failed child shouldn't take down the parent; the parent decides what to do
            logger.error(f"[{child_node.label}] failed: {e}")
            return f"Subagent failed: {e}", True

        logger.info(f"✅ {child_node.label} done: {child_node.total_tokens():,} tokens")
        # Enforced in code because the prompt's size limit is only a request
        if len(summary) > MAX_SUMMARY_CHARS:
            summary = f"{summary[:MAX_SUMMARY_CHARS]}\n... [summary truncated]"
        return summary, False


def build_usage_tree(node: AgentNode, tree: Tree | None = None) -> Tree:
    """Render the agent tree with each agent's own usage and last request size."""
    label = (
        f"[bold]{node.label}[/bold]  {node.tracker.get_total_tokens():,} tokens"
        f"  [dim](last request {node.context_tokens:,} input)[/dim]"
    )
    branch = tree.add(label) if tree else Tree(label)
    for child in sorted(node.children, key=lambda c: c.label):
        build_usage_tree(child, branch)
    return branch


def main() -> None:
    """Main orchestration function."""
    console = Console()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[yellow]Set ANTHROPIC_API_KEY to run this script.[/yellow]")
        return

    tasks = [
        "Compare how 03-chat, 04-tool-use, and 05-agent-loop each manage message history. "
        "What does each add over the one before it?",
        "Summarize what a learner builds in each tutorial of this module, one line each.",
        "What model does 01-simple-llm-call use in its Anthropic script?",
    ]
    examples = "\n".join(f"  {i}. {task[:76]}" for i, task in enumerate(tasks, 1))
    console.print(
        Panel(
            f"Pick an example or type your own task:\n{examples}\n\nType 'quit' to exit.",
            title="Subagents (Anthropic)",
            subtitle=f"Exploring {EXPLORE_ROOT.name}",
        )
    )

    client = anthropic.Anthropic()
    grand_total = 0
    try:
        while True:
            console.print("\n[bold green]You:[/bold green] ", end="")
            user_input = input().strip()
            if user_input.lower() in ("exit", "quit", "q", ""):
                break
            if user_input.isdigit() and 1 <= int(user_input) <= len(tasks):
                user_input = tasks[int(user_input) - 1]

            root = AgentNode(label="parent")
            agent = Agent(client, DelegationBudget(DelegationLimits()), root)
            answer = agent.run(user_input)

            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(answer))
            console.print(build_usage_tree(root))

            child_tokens = root.total_tokens() - root.tracker.get_total_tokens()
            console.print(
                f"Children used [bold]{child_tokens:,}[/bold] tokens that never entered the "
                f"parent's context. The parent's last request was "
                f"[bold]{root.context_tokens:,}[/bold] input tokens."
            )
            grand_total += root.total_tokens()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Interrupted.[/yellow]")
    except anthropic.APIError as e:
        logger.error(f"API error: {e}")

    logger.info(f"Token Usage — Total across all agents: {grand_total:,}")


if __name__ == "__main__":
    main()
