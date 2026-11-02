"""Layer: compaction. Lets a long loop replace its older turns with a summary."""

import json
from dataclasses import dataclass, field
from typing import Any

import anthropic

from common import AnthropicTokenTracker, setup_logging

logger = setup_logging(__name__)

MAX_SERIALIZED_RESULT_CHARS = 8_000

SUMMARY_PROMPT = """Summarize this agent session so the work can continue from the summary alone.
The agent will not see any of these turns again, so anything you leave out is lost.

Keep exact identifiers, numbers, file paths, and error messages. Record:
1. What has been done, and every significant finding
2. Decisions made and why
3. What remains to be done

Reply with the summary only.

<session>
{session}
</session>"""


def block_field(block: Any, name: str) -> Any:
    """Read a field from a content block, whether it's an SDK object or a plain dict."""
    return block[name] if isinstance(block, dict) else getattr(block, name, None)


def is_tool_round_start(message: dict[str, Any]) -> bool:
    """A round starts at an assistant message that requests tools."""
    if message["role"] != "assistant" or isinstance(message["content"], str):
        return False
    return any(block_field(b, "type") == "tool_use" for b in message["content"])


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


@dataclass
class Compactor:
    """Decides when to compact and builds the shorter history."""

    client: anthropic.AsyncAnthropic
    model: str
    threshold_tokens: int
    betas: list[str]
    keep_recent_rounds: int = 1
    compactions: list[str] = field(default_factory=list)

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
        return self.context_tokens(usage) > self.threshold_tokens

    async def compact(
        self,
        label: str,
        task: str,
        messages: list[dict[str, Any]],
        tracker: AnthropicTokenTracker,
    ) -> list[dict[str, Any]] | None:
        """Return a shorter history, or None if there's nothing old enough to summarize."""
        round_starts = [i for i, m in enumerate(messages) if is_tool_round_start(m)]
        # Require two old rounds, so a budget that's too small can't trigger this every round
        if len(round_starts) < self.keep_recent_rounds + 2:
            return None
        split = round_starts[-self.keep_recent_rounds] if self.keep_recent_rounds else len(messages)

        response = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            output_config={"effort": "low"},
            betas=self.betas,
            fallbacks="default",
            messages=[
                {
                    "role": "user",
                    "content": SUMMARY_PROMPT.format(session=serialize_turns(messages[:split])),
                }
            ],
        )
        tracker.track(response.usage)
        summary = "\n".join(b.text for b in response.content if b.type == "text")
        if not summary:
            return None

        before = len(messages)
        anchor = (
            f"{task}\n\n<progress_summary>\nEarlier turns were compacted into this summary:\n"
            f"{summary}\n</progress_summary>"
        )
        compacted = [
            {"role": "user", "content": anchor},
            *[strip_thinking(m) for m in messages[split:]],
        ]
        self.compactions.append(f"{label}: {before} → {len(compacted)} messages")
        logger.info(f"🗜️  [{label}] compacted {before} → {len(compacted)} messages")
        return compacted
