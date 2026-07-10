"""
Hooks & Lifecycle (OpenAI)

The same hook registry as the Anthropic version, driven through the OpenAI
Responses API. Hooks fire at three lifecycle events:

  - pre_tool_use  — inspect a tool call before it runs; allow, deny, or rewrite it
  - post_tool_use — observe the result (logging, metrics, redaction)
  - stop          — the loop finished; final wrap-up

Guardrails and logging live as pluggable hooks, not conditionals in the loop.
"""

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import OpenAITokenTracker

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
        "type": "function",
        "name": "read_file",
        "description": "Read the contents of a file at the given path.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "The file path to read"}},
            "additionalProperties": False,
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "bash",
        "description": "Execute a bash command and return its output.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The command to run"}},
            "additionalProperties": False,
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

    def __init__(self, hooks: HookRegistry, model: str = "gpt-4.1"):
        self.client = OpenAI()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = OpenAITokenTracker()
        self.hooks = hooks

    def _run_tool(self, name: str, args: dict[str, Any]) -> str:
        """Fire pre/post hooks around a single tool execution."""
        decision = self.hooks.run_pre_tool_use(name, args)
        if not decision.allow:
            logger.warning(f"⛔ Denied {name}: {decision.reason}")
            return f"Tool call denied by policy: {decision.reason}"
        tool_input = decision.tool_input or args
        result = execute_tool(name, tool_input)
        self.hooks.run_post_tool_use(name, tool_input, result)
        return result

    def run(self, task: str) -> str:
        """Execute the agent loop for the given task."""
        logger.info(f"Task: {task}")
        input_messages: list[Any] = [{"role": "user", "content": task}]
        previous_response_id: str | None = None

        for iteration in range(self.max_iterations):
            logger.info(f"--- Iteration {iteration + 1} ---")
            response = self.client.responses.create(
                model=self.model,
                tools=TOOLS,
                instructions=SYSTEM_PROMPT,
                input=input_messages,
                **({"previous_response_id": previous_response_id} if previous_response_id else {}),
            )
            if response.usage:
                self.token_tracker.track(response.usage)
            if response.output_text:
                logger.info(f"🤖 Agent: {response.output_text}")

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                final = response.output_text or "Done"
                self.hooks.run_stop(final)
                return final

            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError as e:
                    args = {}
                    logger.error(f"Invalid tool arguments: {e}")
                result = self._run_tool(call.name, args)
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"result": result}),
                    }
                )

            previous_response_id = response.id
            input_messages = tool_outputs

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
            title="Hooks & Lifecycle (OpenAI)",
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
