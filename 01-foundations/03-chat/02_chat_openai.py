"""
Interactive Chat (OpenAI)

Demonstrates an interactive chat loop with a simple message history management.
"""

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common import OpenAITokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)


class ChatSession:
    """
    Chat agent that maintains conversation history and encapsulates all chat logic including message management and API interaction.
    """

    def __init__(self, model: str, token_callback: OpenAITokenTracker):
        """
        Initialize the chat session.
        """
        self.client = OpenAI()
        self.token_callback = token_callback
        self.messages: list[dict[str, str]] = []
        self.model = model

    def send_message(self, user_message: str) -> str:
        """
        Send a message and get a response using the Responses API.
        """
        # Add user message to history
        self.messages.append({"role": "user", "content": user_message})

        logger.info("Sending message to OpenAI (history length: %d)", len(self.messages))

        # Make API call with full message history using Responses API
        response = self.client.responses.create(
            model=self.model,
            temperature=0.1,
            max_output_tokens=2048,
            input=self.messages,
        )

        # Track token usage
        self.token_callback.track(response.usage)

        # Extract assistant's response using new output_text property
        assistant_message = response.output_text or ""

        # Add assistant's response to history
        self.messages.append({"role": "assistant", "content": assistant_message})

        return assistant_message


def main() -> None:
    """
    Main orchestration function that handles user interaction and coordinates the chat flow.
    """

    # Rich console for beautiful output
    console = Console()
    # Create token tracker and chat session
    token_tracker = OpenAITokenTracker()
    chat = ChatSession("gpt-4o", token_tracker)

    # Welcome message
    console.print(
        Panel(
            "[bold cyan]Welcome to OpenAI Chat![/bold cyan]\n\n"
            "Type your messages and press Enter.\n"
            "Type 'quit' or 'exit' to end the conversation.",
            title="Chat Session",
        )
    )

    # Chat loop
    while True:
        # Get user input
        console.print("\n[bold green]You:[/bold green] ", end="")
        user_input = input().strip()

        if user_input.lower() in ["quit", "exit", ""]:
            console.print("\n[yellow]Ending chat session...[/yellow]")
            break

        # Send message and get response
        try:
            response = chat.send_message(user_input)

            # Display response with markdown formatting
            console.print("\n[bold blue]GPT:[/bold blue]")
            console.print(Markdown(response))

        except Exception as e:
            logger.error("Error during chat: %s", e)
            console.print(f"\n[red]Error: {e}[/red]")
            break

    # Report final token usage
    console.print()
    token_tracker.report()
    console.print(f"\n[dim]Total messages exchanged: {len(chat.messages)}[/dim]")


if __name__ == "__main__":
    main()
