"""
Context Compaction (OpenAI)

The same idea on OpenAI's Responses API, where the catch is previous_response_id: when the server
holds the conversation, you have nothing to compact. So this loop keeps its own list of input
items, sets store=False, and sends the whole list on each request. Compacting is then just
sending a shorter list.
"""

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any

import openai
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import OpenAITokenTracker, setup_logging
from shared.incident_data import SERVICES, read_service_logs

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

MODEL = "gpt-4.1"
MAX_ITERATIONS = 25

# Artificially low so compaction triggers in the demo
COMPACT_THRESHOLD_TOKENS = 15_000
KEEP_RECENT_ROUNDS = 1
MAX_SERIALIZED_RESULT_CHARS = 8_000

SYSTEM_PROMPT = """You are an on-call engineer investigating a production incident.

Read one service's logs per turn. Note anything relevant as you go, in a sentence or two, because
earlier logs may later be replaced by a summary. Finish with a report giving the root cause, the
timeline, the customer impact, and the deploy or config change responsible."""

TOOLS: list[Any] = [
    {
        "type": "function",
        "name": "read_logs",
        "description": "Read recent logs for one service. Logs are long.",
        "parameters": {
            "type": "object",
            "properties": {"service": {"type": "string", "enum": SERVICES}},
            "required": ["service"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]

SUMMARY_PROMPT = """Summarize this agent session so the work can continue from the summary alone.
The agent will not see any of these turns again, so anything you leave out is lost.

Keep exact identifiers, numbers, timestamps, and error messages. Record:
1. What has been done, and every significant finding
2. Decisions made and why
3. What remains to be done

Reply with the summary only.

<session>
{session}
</session>"""

TASK = (
    "Payments were failing this afternoon. Investigate by reading the logs of every service: "
    f"{', '.join(SERVICES)}. Then write the incident report."
)


def find_safe_split(items: list[dict[str, Any]], keep_recent_rounds: int) -> int | None:
    """Cut before a round's first function_call, so no call is separated from its output."""
    round_starts = [
        i
        for i, item in enumerate(items)
        if item.get("type") == "function_call"
        and (i == 0 or items[i - 1].get("type") != "function_call")
    ]
    # Require two old rounds: summarizing just one saves little, and if the budget is too small
    # for the summary itself, this stops the loop paying for a compaction on every round
    if len(round_starts) < keep_recent_rounds + 2:
        return None
    if not keep_recent_rounds:
        return len(items)
    split = round_starts[-keep_recent_rounds]
    # On reasoning models, a function_call can't be sent without the reasoning item before it
    return split - 1 if items[split - 1].get("type") == "reasoning" else split


def serialize_items(items: list[dict[str, Any]]) -> str:
    """Render old items as plain text for the summarizer."""
    lines: list[str] = []
    for item in items:
        kind = item.get("type")
        if kind == "function_call":
            lines.append(f"[tool call] {item['name']}({item['arguments']})")
        elif kind == "function_call_output":
            lines.append(f"[tool result] {item['output'][:MAX_SERIALIZED_RESULT_CHARS]}")
        elif isinstance(item.get("content"), str):
            lines.append(f"[{item.get('role')}] {item['content']}")
        elif kind == "message":
            text = " ".join(part.get("text", "") for part in item.get("content", []))
            lines.append(f"[{item.get('role')}] {text}")
    return "\n".join(lines)


@dataclass(frozen=True)
class CompactionEvent:
    """A record of one compaction, for the session report."""

    iteration: int
    items_before: int
    items_after: int


class CompactingAgent:
    """Responses API loop that owns its history so it can resend a compacted input."""

    def __init__(self, compaction_enabled: bool = True) -> None:
        self.client = openai.OpenAI()
        self.token_tracker = OpenAITokenTracker()
        self.compaction_enabled = compaction_enabled
        self.context_history: list[int] = []
        self.compaction_events: list[CompactionEvent] = []

    def summarize(self, items: list[dict[str, Any]]) -> str:
        """Ask the model for a summary, with no tools."""
        response = self.client.responses.create(
            model=MODEL,
            store=False,
            input=SUMMARY_PROMPT.format(session=serialize_items(items)),
        )
        if response.usage:
            self.token_tracker.track(response.usage)
        return str(response.output_text)

    def compact(self, task: str, items: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Return a shorter input list, or None if there's nothing old enough to summarize."""
        split = find_safe_split(items, KEEP_RECENT_ROUNDS)
        if split is None:
            return None
        summary = self.summarize(items[:split])
        if not summary:
            return None
        anchor = (
            f"{task}\n\n<progress_summary>\nEarlier turns were compacted into this summary:\n"
            f"{summary}\n</progress_summary>"
        )
        return [{"role": "user", "content": anchor}, *items[split:]]

    def run(self, task: str) -> str:
        """Execute the agent loop for one task."""
        items: list[Any] = [{"role": "user", "content": task}]

        for iteration in range(1, MAX_ITERATIONS + 1):
            response = self.client.responses.create(
                model=MODEL,
                instructions=SYSTEM_PROMPT,
                tools=TOOLS,
                input=items,
                # One log per turn gives the demo a long loop to compact
                parallel_tool_calls=False,
                # No server-side history: this list is the only copy of the conversation
                store=False,
            )
            usage_tokens = response.usage.input_tokens if response.usage else 0
            if response.usage:
                self.token_tracker.track(response.usage)
            self.context_history.append(usage_tokens)
            logger.info(f"Iteration {iteration}: request used {usage_tokens:,} input tokens")

            items.extend(item.model_dump(exclude_none=True) for item in response.output)
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                return response.output_text or "(no text returned)"

            for call in calls:
                logger.info(f"🔧 {call.name}({call.arguments})")
                try:
                    output = read_service_logs(json.loads(call.arguments)["service"])
                except ValueError as e:
                    output = f"Error: {e}"
                items.append(
                    {"type": "function_call_output", "call_id": call.call_id, "output": output}
                )

            # Compact only here, at a round boundary: every call has its output
            if self.compaction_enabled and usage_tokens > COMPACT_THRESHOLD_TOKENS:
                compacted = self.compact(task, items)
                if compacted:
                    event = CompactionEvent(iteration, len(items), len(compacted))
                    self.compaction_events.append(event)
                    logger.info(f"🗜️  Compacted {len(items)} → {len(compacted)} input items")
                    items = compacted

        return "Stopped: reached the iteration limit before finishing."


def build_report(agent: CompactingAgent) -> Table:
    """Show how the request size changed across the run."""
    compacted_after = {e.iteration for e in agent.compaction_events}
    table = Table(title=f"Input tokens per request (budget {COMPACT_THRESHOLD_TOKENS:,})")
    table.add_column("Iteration", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("")
    peak = max(agent.context_history, default=1)
    for i, tokens in enumerate(agent.context_history, 1):
        marker = "  🗜️ compacted after this" if i in compacted_after else ""
        table.add_row(str(i), f"{tokens:,}", "█" * (tokens * 30 // peak) + marker)
    return table


def main() -> None:
    """Main orchestration function."""
    parser = argparse.ArgumentParser(description="Agent that compacts its own history")
    parser.add_argument("--no-compaction", action="store_true", help="Let the history grow")
    args = parser.parse_args()
    console = Console()

    if not os.environ.get("OPENAI_API_KEY"):
        console.print("[yellow]Set OPENAI_API_KEY to run this script.[/yellow]")
        return

    mode = "off" if args.no_compaction else f"on, above {COMPACT_THRESHOLD_TOKENS:,} tokens"
    console.print(Panel(f"{TASK}\n\nCompaction: {mode}", title="Task"))

    agent = CompactingAgent(compaction_enabled=not args.no_compaction)
    try:
        answer = agent.run(TASK)
        console.print("\n[bold blue]Agent:[/bold blue]")
        console.print(Markdown(answer))
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Interrupted.[/yellow]")
    except openai.APIError as e:
        logger.error(f"API error: {e}")

    console.print(build_report(agent))
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
