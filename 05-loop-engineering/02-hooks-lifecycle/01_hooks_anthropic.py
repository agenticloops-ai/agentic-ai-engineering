"""
Hooks & Lifecycle (Anthropic)

Add control points to the agent loop without rewriting it. A small hook registry
fires callbacks at three lifecycle events:

  - pre_tool_use  — inspect a tool call before it runs; allow, deny, or rewrite it
  - post_tool_use — observe the result (logging, metrics, redaction)
  - stop          — the loop finished; final wrap-up

The payoff: guardrails and logging become pluggable hooks instead of tangled
conditionals inside the loop.
"""

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
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

PRE_TOOL_USE = "pre_tool_use"
POST_TOOL_USE = "post_tool_use"
STOP = "stop"

BLOCKED_COMMANDS = ["rm", "sudo", "chmod", "chown", "mkfs", "dd", "shutdown", "reboot", ">", ">>"]

SYSTEM_PROMPT = """You are a coding agent. Use the provided tools to complete tasks.
Read files before modifying them and summarize what you did when finished."""

TOOLS = [
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


@dataclass
class HookDecision:
    """Verdict a pre_tool_use hook returns. Deny blocks the call; tool_input rewrites it."""

    allow: bool = True
    reason: str = ""
    tool_input: dict[str, Any] | None = None


@dataclass
class HookRegistry:
    """Maps lifecycle events to ordered lists of callbacks."""

    hooks: dict[str, list[Callable[..., Any]]] = field(
        default_factory=lambda: {PRE_TOOL_USE: [], POST_TOOL_USE: [], STOP: []}
    )

    def register(self, event: str, fn: Callable[..., Any]) -> None:
        """Attach a callback to a lifecycle event."""
        self.hooks[event].append(fn)

    def run_pre_tool_use(self, name: str, tool_input: dict[str, Any]) -> HookDecision:
        """Run pre-tool hooks; first denial wins, rewrites chain through."""
        for fn in self.hooks[PRE_TOOL_USE]:
            decision = fn(name, tool_input)
            if decision is None:
                continue
            if not decision.allow:
                return decision
            if decision.tool_input is not None:
                tool_input = decision.tool_input
        return HookDecision(allow=True, tool_input=tool_input)

    def run_post_tool_use(self, name: str, tool_input: dict[str, Any], result: str) -> None:
        """Run observation hooks after a tool executes."""
        for fn in self.hooks[POST_TOOL_USE]:
            fn(name, tool_input, result)

    def run_stop(self, final: str) -> None:
        """Run hooks once the loop is done."""
        for fn in self.hooks[STOP]:
            fn(final)


def block_dangerous_commands(name: str, tool_input: dict[str, Any]) -> HookDecision | None:
    """Guardrail hook: deny bash commands containing blocked tokens."""
    if name != "bash":
        return None
    lowered = tool_input.get("command", "").lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked in lowered:
            return HookDecision(allow=False, reason=f"blocked token '{blocked}'")
    return None


def log_tool_call(name: str, tool_input: dict[str, Any]) -> HookDecision | None:
    """Logging hook: record every attempted tool call."""
    logger.info(f"🪝 pre_tool_use: {name}({json.dumps(tool_input)})")
    return None


def log_tool_result(name: str, tool_input: dict[str, Any], result: str) -> None:
    """Logging hook: record every tool result length."""
    logger.info(f"🪝 post_tool_use: {name} -> {len(result)} chars")


def execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool and return the result as a string."""
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


class HookedAgent:
    """Agent loop with lifecycle hooks fired around every tool call."""

    def __init__(self, hooks: HookRegistry, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = AnthropicTokenTracker()
        self.hooks = hooks

    def _run_tool(self, block: ToolUseBlock) -> str:
        """Fire pre/post hooks around a single tool execution."""
        decision = self.hooks.run_pre_tool_use(block.name, dict(block.input))
        if not decision.allow:
            logger.warning(f"⛔ Denied {block.name}: {decision.reason}")
            return f"Tool call denied by policy: {decision.reason}"
        tool_input = decision.tool_input or dict(block.input)
        result = execute_tool(block.name, tool_input)
        self.hooks.run_post_tool_use(block.name, tool_input, result)
        return result

    def run(self, task: str) -> str:
        """Execute the agent loop for the given task."""
        logger.info(f"Task: {task}")
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

        for iteration in range(self.max_iterations):
            logger.info(f"--- Iteration {iteration + 1} ---")
            response = self.client.messages.create(
                model=self.model,
                temperature=0.1,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            assistant_content = []
            for block in response.content:
                if isinstance(block, TextBlock):
                    logger.info(f"🤖 Agent: {block.text}")
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
                final = response.content[0].text if response.content else "Done"
                self.hooks.run_stop(final)
                return final

            tool_results = []
            for block in response.content:
                if isinstance(block, ToolUseBlock):
                    result = self._run_tool(block)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result}
                    )
            messages.append({"role": "user", "content": tool_results})

        return "Max iterations reached"


def build_registry() -> HookRegistry:
    """Wire the built-in guardrail and logging hooks."""
    registry = HookRegistry()
    registry.register(PRE_TOOL_USE, log_tool_call)
    registry.register(PRE_TOOL_USE, block_dangerous_commands)
    registry.register(POST_TOOL_USE, log_tool_result)
    registry.register(STOP, lambda final: logger.info("🪝 stop: loop finished"))
    return registry


def main() -> None:
    """Interactive CLI showing hooks intercept and guard tool calls."""
    console = Console()
    agent = HookedAgent(build_registry())
    console.print(
        Panel(
            "Every tool call passes through hooks: logged, then guarded.\n\n"
            "Try:\n"
            "  - Show me the files in this directory\n"
            "  - Delete everything with rm -rf .   (watch it get denied)\n\n"
            "Type 'quit' to exit.",
            title="Hooks & Lifecycle (Anthropic)",
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
            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(response))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
