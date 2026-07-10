"""
Context Compaction (Anthropic)

A long-running agent loop that compacts its own history mid-run. When the running
transcript grows past a token budget, the agent summarizes the work so far and
rebuilds its message list — pinning the original task, dropping the bulky
tool traffic, and continuing.

Compaction only fires at a turn boundary (right after tool results are appended),
so an assistant `tool_use` block is never separated from its `tool_result` — the
mistake that makes the Messages API return a 400.

This builds on Context Engineering (03-advanced-techniques/03-context-engineering),
which covers token counting and window strategies for a chat session; here the
angle is compaction as a loop-lifecycle event.
"""

import json
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

# Deliberately small so compaction triggers within a short demo session.
COMPACT_TOKEN_BUDGET = 3000

SYSTEM_PROMPT = """You are a coding agent working through a multi-step task. Use the
tools as needed and give a brief final summary when done."""

SUMMARIZER_PROMPT = """Summarize the following agent transcript so the agent can
continue without the full history. Preserve: the goal, decisions made, files and
commands touched, key findings, and what remains to do. Be concise."""

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


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate (~4 chars/token) over the serialized message list."""
    return len(json.dumps(messages, default=str)) // 4


class CompactingAgent:
    """Agent loop that summarizes and rebuilds its history when it grows too large."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_iterations = 20
        self.token_tracker = AnthropicTokenTracker()
        self.compactions = 0

    def _summarize(self, task: str, messages: list[dict[str, Any]]) -> str:
        """Ask the model to compress the transcript into a progress summary."""
        transcript = json.dumps(messages, default=str, indent=2)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SUMMARIZER_PROMPT,
            messages=[{"role": "user", "content": f"Goal: {task}\n\nTranscript:\n{transcript}"}],
        )
        self.token_tracker.track(response.usage)
        summary = response.content[0].text if response.content else ""
        return summary

    def _compact(self, task: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Collapse history into a single primed user message (task + progress summary).

        Called only at a turn boundary, so no open tool_use/tool_result pair is split.
        """
        self.compactions += 1
        summary = self._summarize(task, messages)
        logger.info(f"🗜️  Compaction #{self.compactions}: {len(messages)} msgs -> 1")
        return [
            {
                "role": "user",
                "content": (
                    f"{task}\n\n[Progress summary so far]:\n{summary}\n\nContinue the task."
                ),
            }
        ]

    def run(self, task: str) -> str:
        """Execute the agent loop, compacting whenever the transcript exceeds the budget."""
        logger.info(f"Task: {task}")
        self.compactions = 0
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

        for iteration in range(self.max_iterations):
            # Lifecycle event: compact at the turn boundary before calling the model.
            if len(messages) > 2 and estimate_tokens(messages) > COMPACT_TOKEN_BUDGET:
                messages = self._compact(task, messages)

            logger.info(f"--- Iteration {iteration + 1} (~{estimate_tokens(messages)} tok) ---")
            response = self.client.messages.create(
                model=self.model,
                temperature=0.1,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            assistant_content: list[dict[str, Any]] = []
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
                return response.content[0].text if response.content else "Done"

            tool_results = []
            for block in response.content:
                if isinstance(block, ToolUseBlock):
                    result = execute_tool(block.name, block.input)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result}
                    )
            # Appending results keeps every tool_use paired with its tool_result.
            messages.append({"role": "user", "content": tool_results})

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
            title="Context Compaction (Anthropic)",
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
