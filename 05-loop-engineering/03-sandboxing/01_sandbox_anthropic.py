"""
Sandboxing (Anthropic)

An agent that writes Python and runs it — but never on the bare host. Every
snippet goes through a sandbox (Docker when available, else a resource-limited
subprocess). The loop is unchanged from Foundations; only the execution tool is
hardened.

See sandbox.py for the two backends and what each actually protects against.
"""

from typing import Any

import anthropic
from anthropic.types import TextBlock, ToolUseBlock
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import AnthropicTokenTracker
from sandbox import docker_available, run_sandboxed

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

SYSTEM_PROMPT = """You are a data/coding agent. To compute anything, write a small
Python program and run it with run_python — you cannot access the host directly.
Print results to stdout. If a run fails or times out, fix the code and retry."""

TOOLS = [
    {
        "name": "run_python",
        "description": "Run a self-contained Python snippet in an isolated sandbox and "
        "return its stdout/stderr. No network, limited CPU and memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The Python source to execute"}
            },
            "required": ["code"],
        },
    }
]


def execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Dispatch the sandboxed execution tool."""
    if name == "run_python":
        result = run_sandboxed(tool_input["code"])
        logger.info(f"🔒 Sandbox [{result.backend}] exit={result.returncode}")
        return result.render()
    return f"Unknown tool: {name}"


class SandboxedAgent:
    """Agent whose code-execution tool runs only inside a sandbox."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = AnthropicTokenTracker()

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
                    logger.info(f"🔧 {block.name}")
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
                    result = execute_tool(block.name, block.input)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result}
                    )
            messages.append({"role": "user", "content": tool_results})

        return "Max iterations reached"


def main() -> None:
    """Interactive CLI running agent-written code in a sandbox."""
    console = Console()
    backend = "docker" if docker_available() else "subprocess + rlimits"
    agent = SandboxedAgent()
    console.print(
        Panel(
            f"Agent-written Python runs in a sandbox (backend: {backend}).\n\n"
            "Try:\n"
            "  - What are the first 15 Fibonacci numbers?\n"
            "  - Estimate pi with a Monte Carlo simulation of 1M points\n\n"
            "Type 'quit' to exit.",
            title="Sandboxing (Anthropic)",
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
