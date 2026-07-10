"""
Subagents & Delegation (OpenAI)

The same orchestrator/worker split as the Anthropic version, driven through the
OpenAI Responses API. The parent's only tool is spawn_subagent; each subagent runs
in its own Responses chain with worker tools and returns a summary. The parent
sees summaries, not transcripts.

Guards: a fan-out cap, and workers that cannot themselves delegate (depth 1).
Child token usage aggregates into the parent's tracker.
"""

import json
import subprocess
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

MAX_SUBAGENTS = 5

ORCHESTRATOR_PROMPT = """You are an orchestrator. Break the user's request into
independent subtasks and delegate each to a subagent with spawn_subagent(task, role).
Each subagent has its own isolated context and returns a summary. Do the work through
subagents, then synthesize their summaries into one final answer."""

WORKER_PROMPT = """You are a focused worker with the role: {role}. Complete the
assigned subtask using your tools and return a concise summary of your findings."""

WORKER_TOOLS = [
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

SPAWN_TOOL = {
    "type": "function",
    "name": "spawn_subagent",
    "description": "Delegate a subtask to a fresh subagent with isolated context. "
    "Returns the subagent's summary.",
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "The subtask to delegate"},
            "role": {"type": "string", "description": "The subagent's role, e.g. 'analyzer'"},
        },
        "additionalProperties": False,
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

    def __init__(self, model: str = "gpt-4.1"):
        self.client = OpenAI()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = OpenAITokenTracker()
        self.subagent_count = 0

    def spawn_subagent(self, task: str, role: str) -> str:
        """Run a fresh subagent to completion and return its summary (isolated context)."""
        if self.subagent_count >= MAX_SUBAGENTS:
            return f"Error: subagent limit ({MAX_SUBAGENTS}) reached"
        self.subagent_count += 1
        logger.info(f"🧑‍🚀 Subagent #{self.subagent_count} [{role}]: {task[:80]}")

        input_messages: list[Any] = [{"role": "user", "content": task}]
        previous_response_id: str | None = None
        for _ in range(self.max_iterations):
            response = self.client.responses.create(
                model=self.model,
                tools=WORKER_TOOLS,
                instructions=WORKER_PROMPT.format(role=role),
                input=input_messages,
                **({"previous_response_id": previous_response_id} if previous_response_id else {}),
            )
            if response.usage:
                self.token_tracker.track(response.usage)

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                return response.output_text or "(no summary)"

            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = execute_worker_tool(call.name, args)
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"result": result}),
                    }
                )
            previous_response_id = response.id
            input_messages = tool_outputs

        return "(subagent hit iteration limit)"

    def run(self, task: str) -> str:
        """Execute the orchestrator loop for the given task."""
        logger.info(f"Task: {task}")
        self.subagent_count = 0
        input_messages: list[Any] = [{"role": "user", "content": task}]
        previous_response_id: str | None = None

        for iteration in range(self.max_iterations):
            logger.info(f"--- Orchestrator iteration {iteration + 1} ---")
            response = self.client.responses.create(
                model=self.model,
                tools=[SPAWN_TOOL],
                instructions=ORCHESTRATOR_PROMPT,
                input=input_messages,
                **({"previous_response_id": previous_response_id} if previous_response_id else {}),
            )
            if response.usage:
                self.token_tracker.track(response.usage)
            if response.output_text:
                logger.info(f"🧭 Orchestrator: {response.output_text}")

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                return response.output_text or "Done"

            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError:
                    args = {"task": "", "role": "worker"}
                summary = self.spawn_subagent(args.get("task", ""), args.get("role", "worker"))
                logger.info(f"📋 Summary: {summary[:100]}")
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"summary": summary}),
                    }
                )
            previous_response_id = response.id
            input_messages = tool_outputs

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
            title="Subagents & Delegation (OpenAI)",
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
