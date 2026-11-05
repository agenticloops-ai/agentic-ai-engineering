"""
Context Compaction (Anthropic)

Demonstrates a long-running loop that compacts its own history mid-run. When a request grows past
a token budget, older turns are summarized and the loop carries on with:

- the frozen system prompt and tools, unchanged
- the original task, pinned word for word
- a summary of the older turns
- the most recent tool rounds, with their thinking blocks removed

The budget is artificially small so that compaction triggers within a single task. Run with
--no-compaction to watch the same task grow without limit.
"""

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, setup_logging
from shared.incident_data import SERVICES, read_service_logs

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
EFFORT = "medium"
MAX_ITERATIONS = 25

# Re-run a safety-declined turn on a fallback model instead of ending the loop
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Artificially low so compaction triggers in the demo; a real agent might use most of its window
COMPACT_THRESHOLD_TOKENS = 15_000
KEEP_RECENT_ROUNDS = 1
MAX_SERIALIZED_RESULT_CHARS = 8_000

SYSTEM_PROMPT = """You are an on-call engineer investigating a production incident.

Read one service's logs per turn. Note anything relevant as you go, in a sentence or two, because
earlier logs may later be replaced by a summary. Finish with a report giving the root cause, the
timeline, the customer impact, and the deploy or config change responsible."""

TOOLS: list[Any] = [
    {
        "name": "read_logs",
        "description": "Read recent logs for one service. Logs are long.",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string", "enum": SERVICES}},
            "required": ["service"],
        },
    }
]

# Tells the summarizer what to retain, since thinking from before the summary is gone for good
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


def block_field(block: Any, name: str) -> Any:
    """Read a field from a content block, whether it's an SDK object or a plain dict."""
    return block[name] if isinstance(block, dict) else getattr(block, name, None)


def is_tool_round_start(message: dict[str, Any]) -> bool:
    """A round starts at an assistant message that requests tools."""
    if message["role"] != "assistant" or isinstance(message["content"], str):
        return False
    return any(block_field(b, "type") == "tool_use" for b in message["content"])


def find_safe_split(messages: list[dict[str, Any]], keep_recent_rounds: int) -> int | None:
    """Find where to cut so a tool_use is never separated from its tool_result."""
    round_starts = [i for i, m in enumerate(messages) if is_tool_round_start(m)]
    # Require two old rounds: summarizing just one saves little, and if the budget is too small
    # for the summary itself, this stops the loop paying for a compaction on every round
    if len(round_starts) < keep_recent_rounds + 2:
        return None
    return round_starts[-keep_recent_rounds] if keep_recent_rounds else len(messages)


def strip_thinking(message: dict[str, Any]) -> dict[str, Any]:
    """Keep a retained turn's text and tool calls, dropping blocks bound to the old history."""
    if isinstance(message["content"], str):
        return message
    kept = []
    for block in message["content"]:
        kind = block_field(block, "type")
        if kind == "text":
            kept.append({"type": "text", "text": block_field(block, "text")})
        elif kind == "tool_use":
            kept.append(
                {
                    "type": "tool_use",
                    "id": block_field(block, "id"),
                    "name": block_field(block, "name"),
                    "input": block_field(block, "input"),
                }
            )
        elif kind == "tool_result":
            kept.append(block)
    return {"role": message["role"], "content": kept}


def serialize_turns(messages: list[dict[str, Any]]) -> str:
    """Render old turns as plain text for the summarizer."""
    lines: list[str] = []
    for message in messages:
        if isinstance(message["content"], str):
            lines.append(f"[{message['role']}] {message['content']}")
            continue
        for block in message["content"]:
            kind = block_field(block, "type")
            if kind == "text":
                lines.append(f"[{message['role']}] {block_field(block, 'text')}")
            elif kind == "tool_use":
                call = json.dumps(block_field(block, "input"))
                lines.append(f"[tool call] {block_field(block, 'name')}({call})")
            elif kind == "tool_result":
                lines.append(f"[tool result] {block['content'][:MAX_SERIALIZED_RESULT_CHARS]}")
    return "\n".join(lines)


def find_pairing_errors(messages: list[dict[str, Any]]) -> list[str]:
    """Check the invariant the API enforces: every tool_use is answered in the next message."""
    errors: list[str] = []
    for i, message in enumerate(messages):
        if isinstance(message["content"], str):
            continue
        blocks = message["content"]
        if message["role"] == "assistant":
            calls = {block_field(b, "id") for b in blocks if block_field(b, "type") == "tool_use"}
            following = messages[i + 1]["content"] if i + 1 < len(messages) else []
            results = (
                {block_field(b, "tool_use_id") for b in following if isinstance(b, dict)}
                if isinstance(following, list)
                else set()
            )
            errors += [f"message {i}: tool_use {c} has no result" for c in calls - results]
        elif i == 0 or messages[i - 1]["role"] != "assistant":
            orphans = [b["tool_use_id"] for b in blocks if b.get("type") == "tool_result"]
            errors += [f"message {i}: tool_result {o} has no tool_use" for o in orphans]
    return errors


@dataclass(frozen=True)
class CompactionEvent:
    """A record of one compaction, for the session report."""

    iteration: int
    tokens_before: int
    messages_before: int
    messages_after: int
    summary_chars: int


class Compactor:
    """Decides when to compact and rewrites the history when it does."""

    def __init__(self, client: anthropic.Anthropic, tracker: AnthropicTokenTracker) -> None:
        self.client = client
        self.tracker = tracker

    @staticmethod
    def context_tokens(usage: Any) -> int:
        """Total size of the last request; cached tokens still occupy the context window."""
        return int(
            usage.input_tokens
            + (usage.cache_read_input_tokens or 0)
            + (usage.cache_creation_input_tokens or 0)
        )

    def should_compact(self, usage: Any) -> bool:
        """Lifecycle check that runs after each tool round, before the next LLM call."""
        return self.context_tokens(usage) > COMPACT_THRESHOLD_TOKENS

    def summarize(self, turns: list[dict[str, Any]]) -> str:
        """Ask the model for a summary, with no tools and low effort."""
        response = self.client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": "low"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
            messages=[
                {
                    "role": "user",
                    "content": SUMMARY_PROMPT.format(session=serialize_turns(turns)),
                }
            ],
        )
        self.tracker.track(response.usage)
        return "\n".join(b.text for b in response.content if b.type == "text")

    def compact(self, task: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Return a shorter history, or None if there's nothing old enough to summarize."""
        split = find_safe_split(messages, KEEP_RECENT_ROUNDS)
        if split is None:
            return None

        summary = self.summarize(messages[:split])
        if not summary:
            logger.warning("Summarizer returned nothing; keeping the full history")
            return None

        # The task is pinned here word for word, so repeated compactions can't paraphrase it away
        anchor = (
            f"{task}\n\n<progress_summary>\nEarlier turns were compacted into this summary:\n"
            f"{summary}\n</progress_summary>"
        )
        compacted = [
            {"role": "user", "content": anchor},
            *[strip_thinking(m) for m in messages[split:]],
        ]

        errors = find_pairing_errors(compacted)
        if errors:
            raise RuntimeError(f"Compaction broke tool pairing: {errors}")
        return compacted


class CompactingAgent:
    """Agent loop that survives past its budget by compacting its own history."""

    def __init__(self, compaction_enabled: bool = True) -> None:
        self.client = anthropic.Anthropic()
        self.token_tracker = AnthropicTokenTracker()
        self.compactor = Compactor(self.client, self.token_tracker) if compaction_enabled else None
        self.context_history: list[int] = []
        self.compaction_events: list[CompactionEvent] = []

    def run(self, task: str) -> str:
        """Execute the agent loop for one task."""
        messages: list[Any] = [{"role": "user", "content": task}]

        for iteration in range(1, MAX_ITERATIONS + 1):
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                output_config={"effort": EFFORT},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                # One log per turn gives the demo a long loop to compact
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                messages=messages,
            )
            self.token_tracker.track(response.usage)
            context = Compactor.context_tokens(response.usage)
            self.context_history.append(context)
            logger.info(f"Iteration {iteration}: request used {context:,} input tokens")
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                text = "\n".join(b.text for b in response.content if b.type == "text")
                return text or f"(no text returned, stop_reason={response.stop_reason})"

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"🔧 {block.name}({json.dumps(block.input)})")
                    try:
                        content = read_service_logs(block.input.get("service", ""))
                        is_error = False
                    except ValueError as e:
                        content, is_error = f"Error: {e}", True
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                            "is_error": is_error,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

            # Compact only here, at a round boundary: no tool_use is waiting on its result
            if self.compactor and self.compactor.should_compact(response.usage):
                messages = self._compact(task, messages, iteration, context)

        return "Stopped: reached the iteration limit before finishing."

    def _compact(
        self, task: str, messages: list[dict[str, Any]], iteration: int, context: int
    ) -> list[dict[str, Any]]:
        """Run a compaction and record what it did, keeping the history if it can't help."""
        assert self.compactor is not None
        compacted = self.compactor.compact(task, messages)
        if compacted is None:
            return messages
        event = CompactionEvent(
            iteration, context, len(messages), len(compacted), len(compacted[0]["content"])
        )
        self.compaction_events.append(event)
        logger.info(f"🗜️  Compacted {event.messages_before} → {event.messages_after} messages")
        return compacted


def demonstrate_pairing(console: Console) -> None:
    """Show offline why the split point matters, using a small example history."""
    history: list[dict[str, Any]] = [{"role": "user", "content": "Investigate."}]
    for i in range(3):
        history += [
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": f"t{i}", "name": "read_logs", "input": {}}],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "log"}],
            },
        ]

    anchor = {"role": "user", "content": "Task + summary"}
    naive = [anchor, *history[len(history) - 3 :]]
    safe_split = find_safe_split(history, keep_recent_rounds=1)
    assert safe_split is not None
    safe = [anchor, *history[safe_split:]]

    table = Table(title="Where you cut matters (no LLM)")
    table.add_column("Strategy")
    table.add_column("Tail starts with")
    table.add_column("Would the API accept it?")
    for name, compacted, start in (
        ("Keep the last 3 messages", naive, "a tool_result"),
        ("find_safe_split", safe, "the assistant's tool_use"),
    ):
        errors = find_pairing_errors(compacted)
        verdict = f"[red]No[/red]: {errors[0]}" if errors else "[green]Yes[/green]"
        table.add_row(name, start, verdict)
    console.print(table)


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

    demonstrate_pairing(console)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("\n[yellow]Set ANTHROPIC_API_KEY to run the live agent.[/yellow]")
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
    except anthropic.APIError as e:
        logger.error(f"API error: {e}")

    console.print(build_report(agent))
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
