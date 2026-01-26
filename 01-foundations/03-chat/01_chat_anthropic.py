"""
Interactive Chat (Anthropic)

Demonstrates an interactive chat loop with a simple message history management.
"""

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common import AnthropicTokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)


class ChatSession:
    """
    Chat agent that maintains conversation history and encapsulates all chat logic including message management and API interaction.
    """

    def __init__(self, model: str, token_callback: AnthropicTokenTracker):
        """
        Initialize the chat session.
        """
        self.client = anthropic.Anthropic()
        self.token_callback = token_callback
        self.messages: list[dict[str, str]] = []
        self.model = model

    def send_message(self, user_message: str) -> str:
        """
        Send a message and get a response.
        """
        # Add user message to history
        self.messages.append({"role": "user", "content": user_message})

        logger.info("Agent processing message (history length: %d)", len(self.messages))

        # Make API call with full message history
        response = self.client.messages.create(
            model=self.model,
            temperature=0.1,
            max_tokens=2048,
            messages=self.messages,
        )

        # Track token usage
        self.token_callback.track(response.usage)

        # Extract assistant's response
        assistant_message = str(response.content[0].text)

        # Add assistant's response to history
        self.messages.append({"role": "assistant", "content": assistant_message})

        return assistant_message

    def get_message_count(self) -> int:
        """Get the total number of messages in the conversation."""
        return len(self.messages)


def main() -> None:
    """
    Main orchestration function that handles user interaction and coordinates the chat flow.
    """
    # Rich console for beautiful output
    console = Console()
    # Create token tracker and chat session
    token_tracker = AnthropicTokenTracker()
    agent = ChatSession("claude-sonnet-4-20250514", token_tracker)

    # Display welcome message
    console.print(
        Panel(
            "[bold cyan]Welcome to Claude Chat![/bold cyan]\n\n"
            "Type your messages and press Enter.\n"
            "Type 'quit' or 'exit' to end the conversation.",
            title="Chat Session",
        )
    )

    # Interactive chat loop
    while True:
        # Get user input
        console.print("\n[bold green]You:[/bold green] ", end="")
        user_input = input().strip()

        if user_input.lower() in ["quit", "exit", ""]:
            console.print("\n[yellow]Ending chat session...[/yellow]")
            break

        # Process message through agent
        try:
            response = agent.send_message(user_input)

            # Display response
            console.print("\n[bold blue]Claude:[/bold blue]")
            console.print(Markdown(response))

        except Exception as e:
            logger.error("Error during chat: %s", e)
            console.print(f"\n[red]Error: {e}[/red]")
            break

    # Display final statistics
    console.print()
    token_tracker.report()
    console.print(f"\n[dim]Total messages exchanged: {agent.get_message_count()}[/dim]")


if __name__ == "__main__":
    main()
