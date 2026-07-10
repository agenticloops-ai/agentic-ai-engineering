"""
Sandboxing (OpenAI)

Same sandboxed code-execution agent as the Anthropic version, driven through the
OpenAI Responses API. The agent writes Python and runs it via run_python, which
executes inside Docker (when available) or a resource-limited subprocess.

See sandbox.py for the two backends and what each actually protects against.
"""

import json
from typing import Any

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import OpenAITokenTracker
from sandbox import docker_available, run_sandboxed

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

SYSTEM_PROMPT = """You are a data/coding agent. To compute anything, write a small
Python program and run it with run_python — you cannot access the host directly.
Print results to stdout. If a run fails or times out, fix the code and retry."""

TOOLS = [
    {
        "type": "function",
        "name": "run_python",
        "description": "Run a self-contained Python snippet in an isolated sandbox and "
        "return its stdout/stderr. No network, limited CPU and memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The Python source to execute"}
            },
            "additionalProperties": False,
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

    def __init__(self, model: str = "gpt-4.1"):
        self.client = OpenAI()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = OpenAITokenTracker()

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
                return response.output_text or "Done"

            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError as e:
                    args = {}
                    logger.error(f"Invalid tool arguments: {e}")
                logger.info(f"🔧 {call.name}")
                result = execute_tool(call.name, args)
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
            title="Sandboxing (OpenAI)",
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
