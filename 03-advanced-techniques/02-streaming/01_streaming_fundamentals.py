"""
Streaming Fundamentals (Anthropic)

Demonstrates real-time token-by-token streaming with Claude. Covers two approaches:
the simple `.text_stream` iterator for quick wins, and event-based iteration for full
control over the streaming lifecycle.
"""

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from common import AnthropicTokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = (
    "You are a helpful assistant. Keep responses concise and well-structured. "
    "Use markdown formatting — headers, bullet points, bold — for readability."
)


class StreamingChat:
    """Interactive chat with streaming responses rendered in real-time."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker) -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker
        self.messages: list[dict[str, str]] = []

    def stream_simple(self, user_input: str, console: Console) -> str:
        """Stream using the simple .text_stream iterator.

        This is the easiest way to stream — just iterate over text chunks.
        Best for simple use cases where you don't need event-level control.
        """
        self.messages.append({"role": "user", "content": user_input})
        logger.info("Streaming response (simple mode, history: %d messages)", len(self.messages))

        accumulated = ""

        with self.client.messages.stream(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=self.messages,
        ) as stream:
            # .text_stream yields plain text strings — just the content deltas
            with Live(Markdown(""), refresh_per_second=15, console=console) as live:
                for text in stream.text_stream:
                    accumulated += text
                    live.update(Markdown(accumulated))

            # Token usage is available after the stream completes
            final_message = stream.get_final_message()
            self.token_tracker.track(final_message.usage)
            logger.info(
                "Stream complete — input: %d, output: %d tokens",
                final_message.usage.input_tokens,
                final_message.usage.output_tokens,
            )

        self.messages.append({"role": "assistant", "content": accumulated})
        return accumulated

    def stream_with_events(self, user_input: str, console: Console) -> str:
        """Stream using event-based iteration for full lifecycle visibility.

        This approach gives you access to every streaming event: content block
        starts/stops, text deltas, message metadata. Use this when you need
        fine-grained control (e.g., detecting tool calls, tracking block boundaries).
        """
        self.messages.append({"role": "user", "content": user_input})
        logger.info("Streaming response (event mode, history: %d messages)", len(self.messages))

        accumulated = ""

        with self.client.messages.stream(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=self.messages,
        ) as stream:
            with Live(Markdown(""), refresh_per_second=15, console=console) as live:
                for event in stream:
                    # --- Event lifecycle ---
                    # message_start: stream begins, contains model info
                    # content_block_start: a new content block (text, tool_use, etc.)
                    # content_block_delta: incremental content update
                    # content_block_stop: block is complete
                    # message_delta: top-level changes (stop_reason, usage)
                    # message_stop: stream is done

                    if event.type == "content_block_start":
                        logger.debug(
                            "Block started: index=%d, type=%s",
                            event.index,
                            event.content_block.type,
                        )

                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            accumulated += event.delta.text
                            live.update(Markdown(accumulated))

                    elif event.type == "message_delta":
                        logger.debug("Stop reason: %s", event.delta.stop_reason)

            final_message = stream.get_final_message()
            self.token_tracker.track(final_message.usage)
            logger.info(
                "Stream complete — input: %d, output: %d tokens",
                final_message.usage.input_tokens,
                final_message.usage.output_tokens,
            )

        self.messages.append({"role": "assistant", "content": accumulated})
        return accumulated

    def reset(self) -> None:
        """Clear conversation history for a fresh start."""
        self.messages.clear()
        logger.info("Conversation history cleared")


def main() -> None:
    """Interactive streaming chat with mode selection."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    chat = StreamingChat(MODEL, token_tracker)

    console.print(
        Panel(
            "[bold cyan]Streaming Chat[/bold cyan]\n\n"
            "Experience real-time token-by-token streaming with Claude.\n\n"
            "[bold]Two streaming modes:[/bold]\n"
            "  [green]simple[/green]   — .text_stream iterator (easiest, just text)\n"
            "  [green]events[/green]   — event-based iteration (full lifecycle control)\n\n"
            "Type [bold]mode simple[/bold] or [bold]mode events[/bold] to switch.\n"
            "Type [bold]clear[/bold] to reset conversation history.\n"
            "Type [bold]quit[/bold] or [bold]exit[/bold] to end.",
            title="02-streaming / 01 — Streaming Fundamentals",
        )
    )

    mode = "simple"
    console.print(f"\n[dim]Current mode: {mode}[/dim]")

    while True:
        console.print("\n[bold green]You:[/bold green] ", end="")
        try:
            user_input = input().strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Interrupted.[/yellow]")
            break

        if not user_input or user_input.lower() in ("quit", "exit"):
            console.print("[yellow]Ending session...[/yellow]")
            break

        if user_input.lower() == "clear":
            chat.reset()
            console.print("[dim]Conversation cleared.[/dim]")
            continue

        if user_input.lower().startswith("mode "):
            new_mode = user_input.split(" ", 1)[1].strip().lower()
            if new_mode in ("simple", "events"):
                mode = new_mode
                console.print(f"[dim]Switched to {mode} mode.[/dim]")
            else:
                console.print("[red]Unknown mode. Use 'simple' or 'events'.[/red]")
            continue

        try:
            console.print("\n[bold blue]Claude:[/bold blue]")
            if mode == "simple":
                chat.stream_simple(user_input, console)
            else:
                chat.stream_with_events(user_input, console)
        except anthropic.APIError as e:
            logger.error("API error: %s", e)
            console.print(f"\n[red]API error: {e}[/red]")

    console.print()
    token_tracker.report()
    console.print(f"[dim]Messages exchanged: {len(chat.messages)}[/dim]")


if __name__ == "__main__":
    main()
