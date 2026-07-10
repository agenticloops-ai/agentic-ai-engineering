"""
Subagents & Delegation (Anthropic)

A parent (orchestrator) loop whose only tool is spawn_subagent. Each subagent is
a fresh agent with its own message history and worker tools; it runs a subtask to
completion and returns only a summary. The parent's context stays small — it sees
summaries, not the child's full transcript.

Guards: a fan-out cap, and workers that cannot themselves delegate (depth 1).
Child token usage aggregates into the parent's tracker.
"""

import subprocess
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import TextBlock, ToolUseBlock
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import AnthropicTokenTracker

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

MAX_SUBAGENTS = 5

ORCHESTRATOR_PROMPT = """You are an orchestrator. Break the user's request into
independent subtasks and delegate each to a subagent with spawn_subagent(task, role).
Each subagent has its own isolated context and returns a summary. Do the work through
subagents, then synthesize their summaries into one final answer."""

WORKER_PROMPT = """You are a focused worker with the role: {role}. Complete the
assigned subtask using your tools and return a concise summary of your findings."""

WORKER_TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "The file path to read"}},
            "required": ["path"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a bash command and return its output.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The command to run"}},
            "required": ["command"],
        },
    },
]

SPAWN_TOOL = {
    "name": "spawn_subagent",
    "description": "Delegate a subtask to a fresh subagent with isolated context. "
    "Returns the subagent's summary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "The subtask to delegate"},
            "role": {"type": "string", "description": "The subagent's role, e.g. 'analyzer'"},
        },
        "required": ["task", "role"],
    },
}


def execute_worker_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a worker tool (read_file or bash)."""
    if name == "read_file":
        try:
            return Path(tool_input["path"]).read_text()
        except Exception as e:
            return f"Error: {e}"
    if name == "bash":
        try:
            result = subprocess.run(
                tool_input["command"], shell=True, capture_output=True, text=True, timeout=30
            )
            return (result.stdout + result.stderr) or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {e}"
    return f"Unknown tool: {name}"


class OrchestratorAgent:
    """Parent loop that delegates subtasks to isolated subagents."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = AnthropicTokenTracker()
        self.subagent_count = 0

    def spawn_subagent(self, task: str, role: str) -> str:
        """Run a fresh subagent to completion and return its summary (isolated context)."""
        if self.subagent_count >= MAX_SUBAGENTS:
            return f"Error: subagent limit ({MAX_SUBAGENTS}) reached"
        self.subagent_count += 1
        logger.info(f"🧑‍🚀 Subagent #{self.subagent_count} [{role}]: {task[:80]}")

        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        for _ in range(self.max_iterations):
            response = self.client.messages.create(
                model=self.model,
                temperature=0.1,
                max_tokens=2048,
                system=WORKER_PROMPT.format(role=role),
                tools=WORKER_TOOLS,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            assistant_content: list[dict[str, Any]] = []
            for block in response.content:
                if isinstance(block, TextBlock):
                    assistant_content.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                return response.content[0].text if response.content else "(no summary)"

            tool_results = []
            for block in response.content:
                if isinstance(block, ToolUseBlock):
                    result = execute_worker_tool(block.name, block.input)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result}
                    )
            messages.append({"role": "user", "content": tool_results})

        return "(subagent hit iteration limit)"

    def run(self, task: str) -> str:
        """Execute the orchestrator loop for the given task."""
        logger.info(f"Task: {task}")
        self.subagent_count = 0
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

        for iteration in range(self.max_iterations):
            logger.info(f"--- Orchestrator iteration {iteration + 1} ---")
            response = self.client.messages.create(
                model=self.model,
                temperature=0.1,
                max_tokens=4096,
                system=ORCHESTRATOR_PROMPT,
                tools=[SPAWN_TOOL],
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            assistant_content: list[dict[str, Any]] = []
            for block in response.content:
                if isinstance(block, TextBlock):
                    logger.info(f"🧭 Orchestrator: {block.text}")
                    assistant_content.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                return response.content[0].text if response.content else "Done"

            tool_results = []
            for block in response.content:
                if isinstance(block, ToolUseBlock):
                    summary = self.spawn_subagent(block.input["task"], block.input["role"])
                    logger.info(f"📋 Summary: {summary[:100]}")
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": summary}
                    )
            messages.append({"role": "user", "content": tool_results})

        return "Max iterations reached"


def main() -> None:
    """Interactive CLI showing an orchestrator delegating to subagents."""
    console = Console()
    agent = OrchestratorAgent()
    console.print(
        Panel(
            "The orchestrator delegates subtasks to isolated subagents.\n\n"
            "Try:\n"
            "  - Summarize what each Python file in this directory does\n"
            "  - Compare the read_file and bash tools, one subagent each\n\n"
            "Type 'quit' to exit.",
            title="Subagents & Delegation (Anthropic)",
        )
    )

    try:
        while True:
            console.print("\n[bold green]You:[/bold green] ", end="")
            user_input = input().strip()
            if user_input.lower() in ("exit", "quit", "q", ""):
                console.print("\n[yellow]Ending session...[/yellow]")
                break
            response = agent.run(user_input)
            console.print(f"\n[dim]Subagents spawned: {agent.subagent_count}[/dim]")
            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(response))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
