"""
Context Engineering (Anthropic)

Demonstrates context window management with token counting, budget allocation,
and automatic compression via summarization. Uses an artificially low context
budget so compression triggers after just a few exchanges.
"""

from dataclasses import dataclass

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

# Model configuration
MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = (
    "You are a knowledgeable research assistant. You help users explore topics in depth, "
    "building on previous discussion points. When referencing earlier parts of the conversation, "
    "mention specific details to demonstrate continuity."
)

# Artificially low budget so compression triggers quickly in the demo
MAX_CONTEXT_TOKENS = 4096
RESPONSE_RESERVE = 2048
RECENT_MESSAGES_TO_KEEP = 4


@dataclass
class ContextBudget:
    """Token budget allocation across context components."""

    max_context: int
    system_tokens: int = 0
    response_reserve: int = RESPONSE_RESERVE

    @property
    def history_budget(self) -> int:
        """Available tokens for conversation history."""
        return self.max_context - self.system_tokens - self.response_reserve


@dataclass
class TokenSnapshot:
    """Snapshot of token usage for budget display."""

    system: int = 0
    history: int = 0
    history_budget: int = 0
    reserve: int = 0
    message_count: int = 0
    compression_count: int = 0


class ContextManager:
    """Manages context window allocation and conversation compression."""

    def __init__(self, model: str, max_context: int, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker
        self.messages: list[dict] = []
        self.budget = ContextBudget(max_context=max_context)
        self.compression_count = 0

        # Measure system prompt tokens once at init
        self.budget.system_tokens = self._count_tokens([])
        logger.info(
            "Context budget — system: %d, history: %d, reserve: %d",
            self.budget.system_tokens,
            self.budget.history_budget,
            self.budget.response_reserve,
        )

    def chat(self, user_input: str) -> str:
        """Send message, compress if needed, return response."""
        self.messages.append({"role": "user", "content": user_input})

        # Compress before sending if history exceeds budget
        self._compress_if_needed()

        logger.info(
            "Sending request (messages: %d, history tokens: ~%d/%d)",
            len(self.messages),
            self._count_tokens(self.messages) - self.budget.system_tokens,
            self.budget.history_budget,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.budget.response_reserve,
            system=SYSTEM_PROMPT,
            messages=self.messages,
        )

        self.token_tracker.track(response.usage)

        assistant_message = str(response.content[0].text)
        self.messages.append({"role": "assistant", "content": assistant_message})

        return assistant_message

    def _count_tokens(self, messages: list[dict]) -> int:
        """Count tokens using the token counting API."""
        # API requires at least one message — use a minimal placeholder to measure system overhead
        msgs = messages if messages else [{"role": "user", "content": "."}]
        result = self.client.messages.count_tokens(
            model=self.model,
            system=SYSTEM_PROMPT,
            messages=msgs,
        )
        token_count: int = result.input_tokens
        return token_count

    def _compress_if_needed(self) -> None:
        """If history exceeds budget, summarize oldest messages."""
        history_tokens = self._count_tokens(self.messages) - self.budget.system_tokens

        if history_tokens <= self.budget.history_budget:
            return

        logger.info(
            "History (%d tokens) exceeds budget (%d tokens) — compressing",
            history_tokens,
            self.budget.history_budget,
        )

        # Split: keep recent messages verbatim, summarize the rest
        keep_count = min(RECENT_MESSAGES_TO_KEEP, len(self.messages))
        old_messages = self.messages[:-keep_count] if keep_count > 0 else self.messages
        recent_messages = self.messages[-keep_count:] if keep_count > 0 else []

        if not old_messages:
            logger.warning("No messages to compress — budget may be too small")
            return

        old_tokens = self._count_tokens(old_messages) - self.budget.system_tokens

        # Summarize old messages
        summary = self._summarize_messages(old_messages)

        # Replace old messages with summary
        summary_message = {
            "role": "user",
            "content": (
                f"[Previous conversation summary]\n{summary}\n"
                "[End of summary — continue the conversation from here]"
            ),
        }

        # Ensure alternating roles: summary (user) then recent messages
        # If recent_messages starts with a user message, we need an assistant ack
        if recent_messages and recent_messages[0]["role"] == "user":
            self.messages = [
                summary_message,
                {"role": "assistant", "content": "Understood, I have the conversation context."},
                *recent_messages,
            ]
        else:
            self.messages = [summary_message, *recent_messages]

        new_tokens = self._count_tokens(self.messages) - self.budget.system_tokens
        self.compression_count += 1

        logger.info(
            "Compressed %d messages: %d → %d tokens (saved %d tokens)",
            len(old_messages),
            old_tokens,
            new_tokens,
            old_tokens - new_tokens,
        )

    def _summarize_messages(self, messages: list[dict]) -> str:
        """Use LLM to summarize a block of messages."""
        # Build a readable transcript for the summarizer
        transcript = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in messages
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=(
                "Summarize the following conversation concisely. "
                "Preserve key facts, decisions, and specific details the user mentioned. "
                "Write in third person past tense. Be brief but thorough."
            ),
            messages=[{"role": "user", "content": transcript}],
        )

        self.token_tracker.track(response.usage)
        return str(response.content[0].text)

    def get_token_snapshot(self) -> TokenSnapshot:
        """Return current token counts for budget display."""
        history_tokens = 0
        if self.messages:
            history_tokens = self._count_tokens(self.messages) - self.budget.system_tokens

        return TokenSnapshot(
            system=self.budget.system_tokens,
            history=history_tokens,
            history_budget=self.budget.history_budget,
            reserve=self.budget.response_reserve,
            message_count=len(self.messages),
            compression_count=self.compression_count,
        )


def _render_budget_display(console: Console, snapshot: TokenSnapshot) -> None:
    """Render the context budget visualization."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Component", style="dim")
    table.add_column("Tokens", justify="right")
    table.add_column("Bar", min_width=30)

    # History usage bar
    usage_ratio = snapshot.history / snapshot.history_budget if snapshot.history_budget > 0 else 0
    bar_width = 25
    filled = int(usage_ratio * bar_width)
    bar_color = "green" if usage_ratio < 0.7 else "yellow" if usage_ratio < 0.9 else "red"
    bar = f"[{bar_color}]{'█' * filled}[/{bar_color}][dim]{'░' * (bar_width - filled)}[/dim]"

    table.add_row("System", f"[cyan]{snapshot.system:,}[/cyan]", "[dim]fixed[/dim]")
    table.add_row(
        "History",
        f"[{bar_color}]{snapshot.history:,}[/{bar_color}] / {snapshot.history_budget:,}",
        bar,
    )
    table.add_row("Response Reserve", f"[cyan]{snapshot.reserve:,}[/cyan]", "[dim]max_tokens[/dim]")
    table.add_row("Messages", f"[cyan]{snapshot.message_count}[/cyan]", "")

    footer = f"Messages: {snapshot.message_count}"
    if snapshot.compression_count > 0:
        footer += f" │ Compressions: {snapshot.compression_count}"

    console.print(
        Panel(table, title="Context Budget", subtitle=footer, border_style="dim", padding=(0, 1))
    )


def main() -> None:
    """Main orchestration function for the context engineering demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    manager = ContextManager(MODEL, MAX_CONTEXT_TOKENS, token_tracker)

    console.print(
        Panel(
            "[bold cyan]Context Engineering Demo[/bold cyan]\n\n"
            "This chat uses an artificially low context budget "
            f"({MAX_CONTEXT_TOKENS:,} tokens total, "
            f"~{manager.budget.history_budget:,} for history).\n"
            "After a few exchanges, you'll see automatic compression kick in —\n"
            "older messages get summarized to stay within budget.\n\n"
            "Try discussing a topic in depth and watch the budget display.\n"
            "Type [bold]'quit'[/bold] or [bold]'exit'[/bold] to end.",
            title="Research Assistant",
        )
    )

    # Show initial budget
    _render_budget_display(console, manager.get_token_snapshot())

    while True:
        console.print("\n[bold green]You:[/bold green] ", end="")
        user_input = input().strip()

        if user_input.lower() in ["quit", "exit", ""]:
            console.print("\n[yellow]Ending session...[/yellow]")
            break

        try:
            response = manager.chat(user_input)

            console.print("\n[bold blue]Claude:[/bold blue]")
            console.print(Markdown(response))

            # Show budget after each turn
            console.print()
            _render_budget_display(console, manager.get_token_snapshot())

        except Exception as e:
            logger.error("Error during chat: %s", e)
            console.print(f"\n[red]Error: {e}[/red]")
            break

    # Final report
    console.print()
    token_tracker.report()
    console.print(
        f"\n[dim]Messages: {len(manager.messages)} │ "
        f"Compressions: {manager.compression_count}[/dim]"
    )


if __name__ == "__main__":
    main()
