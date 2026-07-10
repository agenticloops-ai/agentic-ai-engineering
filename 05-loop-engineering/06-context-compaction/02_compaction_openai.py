"""
Context Compaction (OpenAI)

A long-running agent loop that compacts its own history mid-run. On the Responses
API, compaction means giving up the server-side conversation chain: instead of
passing `previous_response_id`, we keep the full input list locally so we can
rewrite it. When it grows past a token budget, we summarize and rebuild.

This builds on Context Engineering (03-advanced-techniques/03-context-engineering),
which covers token counting and window strategies for a chat session; here the
angle is compaction as a loop-lifecycle event.
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

# Deliberately small so compaction triggers within a short demo session.
COMPACT_TOKEN_BUDGET = 3000

SYSTEM_PROMPT = """You are a coding agent working through a multi-step task. Use the
tools as needed and give a brief final summary when done."""

SUMMARIZER_PROMPT = """Summarize the following agent transcript so the agent can
continue without the full history. Preserve: the goal, decisions made, files and
commands touched, key findings, and what remains to do. Be concise."""

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


def estimate_tokens(items: list[Any]) -> int:
    """Rough token estimate (~4 chars/token) over the serialized input list."""
    return len(json.dumps(items, default=str)) // 4


class CompactingAgent:
    """Agent loop that summarizes and rebuilds its local input when it grows too large."""

    def __init__(self, model: str = "gpt-4.1"):
        self.client = OpenAI()
        self.model = model
        self.max_iterations = 20
        self.token_tracker = OpenAITokenTracker()
        self.compactions = 0

    def _summarize(self, task: str, items: list[Any]) -> str:
        """Ask the model to compress the transcript into a progress summary."""
        transcript = json.dumps(items, default=str, indent=2)
        response = self.client.responses.create(
            model=self.model,
            instructions=SUMMARIZER_PROMPT,
            input=[{"role": "user", "content": f"Goal: {task}\n\nTranscript:\n{transcript}"}],
        )
        if response.usage:
            self.token_tracker.track(response.usage)
        return response.output_text or ""

    def _compact(self, task: str, items: list[Any]) -> list[Any]:
        """Collapse the local input into a single primed user message (task + summary)."""
        self.compactions += 1
        summary = self._summarize(task, items)
        logger.info(f"🗜️  Compaction #{self.compactions}: {len(items)} items -> 1")
        return [
            {
                "role": "user",
                "content": (
                    f"{task}\n\n[Progress summary so far]:\n{summary}\n\nContinue the task."
                ),
            }
        ]

    def run(self, task: str) -> str:
        """Execute the agent loop, compacting whenever the local input exceeds the budget.

        Note: no previous_response_id — the full input is kept locally so it can be
        rewritten on compaction.
        """
        logger.info(f"Task: {task}")
        self.compactions = 0
        input_messages: list[Any] = [{"role": "user", "content": task}]

        for iteration in range(self.max_iterations):
            # Lifecycle event: compact at the turn boundary before calling the model.
            if len(input_messages) > 2 and estimate_tokens(input_messages) > COMPACT_TOKEN_BUDGET:
                input_messages = self._compact(task, input_messages)

            logger.info(
                f"--- Iteration {iteration + 1} (~{estimate_tokens(input_messages)} tok) ---"
            )
            response = self.client.responses.create(
                model=self.model,
                tools=TOOLS,
                instructions=SYSTEM_PROMPT,
                input=input_messages,
            )
            if response.usage:
                self.token_tracker.track(response.usage)
            if response.output_text:
                logger.info(f"🤖 Agent: {response.output_text}")

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                return response.output_text or "Done"

            # Keep the model's own output items in the local input so tool outputs match.
            input_messages += list(response.output)
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = execute_tool(call.name, args)
                input_messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"result": result}),
                    }
                )

        return "Max iterations reached"


def main() -> None:
    """Interactive CLI demonstrating mid-run context compaction."""
    console = Console()
    agent = CompactingAgent()
    console.print(
        Panel(
            f"This agent compacts its own history past ~{COMPACT_TOKEN_BUDGET} tokens.\n\n"
            "Try a multi-step task that generates lots of tool output:\n"
            "  - Read every Python file here and describe the overall design\n"
            "  - Explore this directory, then summarize the module's structure\n\n"
            "Type 'quit' to exit.",
            title="Context Compaction (OpenAI)",
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
            console.print(f"\n[dim]Compactions this run: {agent.compactions}[/dim]")
            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(response))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
