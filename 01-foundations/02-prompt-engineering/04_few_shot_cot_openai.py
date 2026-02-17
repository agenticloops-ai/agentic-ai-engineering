"""
Few-Shot & Chain-of-Thought Prompting (OpenAI)

Demonstrates three prompting techniques, each on a task where it shines:
1. Zero-shot — sentiment analysis (well-understood task, no examples needed)
2. Few-shot — classification with custom domain labels (teaches YOUR taxonomy)
3. Chain-of-thought — root cause analysis (multi-step reasoning needed)

Each demo shows WHY you'd pick that technique over the others.
"""

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from common import OpenAITokenTracker, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# --- Demo A: Zero-Shot (Sentiment Analysis) ---
# Zero-shot works great when the task is well-understood by the model
REVIEWS = [
    "This laptop is incredible — fast, lightweight, and the battery lasts all day.",
    "The charging cable broke after two weeks. Total waste of money.",
    "It's fine for the price. Nothing special but gets the job done.",
]

# --- Demo B: Few-Shot (Custom Domain Labels) ---
# Few-shot teaches the model YOUR categories that it wouldn't know otherwise
FEW_SHOT_EXAMPLES = [
    ("I was charged twice for the same subscription", "BILLING_DISPUTE"),
    ("Can't log in even after resetting my password three times", "ACCOUNT_ACCESS"),
    ("The export function crashes when the report has more than 1000 rows", "TECHNICAL_BUG"),
    ("It would be great if we could schedule reports to run automatically", "FEATURE_REQUEST"),
]

FEW_SHOT_TEST_INPUTS = [
    "My invoice shows a charge from last month that I already disputed",
    "The dashboard keeps showing a spinning wheel and never loads the charts",
    "Would love to be able to tag tickets with custom labels for our team",
]

# --- Demo C: Chain-of-Thought (Root Cause Analysis) ---
# CoT shines when the task requires multi-step reasoning
BUG_REPORT = (
    "Users report that the app works fine in the morning but becomes extremely slow "
    "after lunch. The slowdown affects all users simultaneously, not just individual "
    "sessions. Restarting the app server temporarily fixes the issue but it returns "
    "within a few hours. Memory usage on the server appears normal."
)


class PromptingClient:
    """Demonstrates zero-shot, few-shot, and chain-of-thought prompting."""

    def __init__(self, model: str, token_tracker: OpenAITokenTracker):
        self.client = OpenAI()
        self.model = model
        self.token_tracker = token_tracker

    def _call(self, instructions: str, user_input: str, max_tokens: int = 256) -> str:
        """Make a single API call and track tokens."""
        response = self.client.responses.create(
            model=self.model,
            temperature=0.0,
            max_output_tokens=max_tokens,
            instructions=instructions,
            input=user_input,
        )
        if hasattr(response, "usage") and response.usage:
            self.token_tracker.track(response.usage)
        return (response.output_text or "").strip()

    # --- Zero-Shot ---
    def classify_sentiment(self, review: str) -> str:
        """Classify sentiment with no examples — the model already understands this task."""
        instructions = (
            "Classify the sentiment of the following product review.\n"
            "Respond with exactly one word: POSITIVE, NEGATIVE, or NEUTRAL."
        )
        return self._call(instructions, review)

    # --- Few-Shot ---
    def classify_ticket_few_shot(self, ticket: str) -> str:
        """Classify with domain-specific labels the model wouldn't know without examples."""
        examples = "\n".join(
            f'Ticket: "{text}"\nCategory: {label}' for text, label in FEW_SHOT_EXAMPLES
        )
        instructions = (
            "Classify support tickets into one of these categories: "
            "BILLING_DISPUTE, ACCOUNT_ACCESS, TECHNICAL_BUG, FEATURE_REQUEST\n\n"
            f"Examples:\n\n{examples}\n\n"
            "Respond with ONLY the category name."
        )
        return self._call(instructions, f'Ticket: "{ticket}"\nCategory:')

    # --- Chain-of-Thought ---
    def analyze_zero_shot(self, bug_report: str) -> str:
        """Analyze a bug report without reasoning guidance — baseline."""
        instructions = (
            "You are a senior engineer. Identify the most likely root cause of this bug.\n"
            "Be concise — one or two sentences."
        )
        return self._call(instructions, bug_report)

    def analyze_cot(self, bug_report: str) -> str:
        """Analyze with chain-of-thought — reason through the problem step by step."""
        instructions = (
            "You are a senior engineer. Analyze this bug report step by step:\n"
            "1. What patterns do you observe? (timing, scope, triggers)\n"
            "2. What does each clue rule in or rule out?\n"
            "3. What is the most likely root cause?\n"
            "4. What would you check first to confirm?\n\n"
            "Think through each step before concluding."
        )
        return self._call(instructions, bug_report, max_tokens=512)


def main() -> None:
    """Run three demos showing when to use each prompting technique."""
    console = Console()
    token_tracker = OpenAITokenTracker()
    client = PromptingClient("gpt-4.1", token_tracker)

    console.print(
        Panel(
            "[bold cyan]Few-Shot & Chain-of-Thought Prompting[/bold cyan]\n\n"
            "Three demos, each using the technique where it shines:\n"
            "  A. Zero-shot — sentiment analysis (task the model already knows)\n"
            "  B. Few-shot — custom label classification (teaching YOUR taxonomy)\n"
            "  C. Chain-of-thought — root cause analysis (multi-step reasoning)",
            title="Prompt Engineering — OpenAI",
        )
    )

    # --- Demo A: Zero-Shot Sentiment ---
    console.print(f"\n[bold magenta]{'═' * 60}[/bold magenta]")
    console.print("[bold magenta]Demo A: Zero-Shot — Sentiment Analysis[/bold magenta]")
    console.print("[dim]No examples needed — the model already understands sentiment.[/dim]\n")

    sentiment_table = Table(show_lines=True)
    sentiment_table.add_column("Review", style="cyan", max_width=55)
    sentiment_table.add_column("Sentiment", style="green", max_width=12)

    for review in REVIEWS:
        try:
            result = client.classify_sentiment(review)
            sentiment_table.add_row(review[:55], result)
        except Exception as e:
            logger.error("Sentiment error: %s", e)
            sentiment_table.add_row(review[:55], "ERROR")

    console.input("\n[dim]Press Enter to continue...[/dim]")
    console.print(sentiment_table)

    # --- Demo B: Few-Shot Custom Labels ---
    console.print(f"\n[bold magenta]{'═' * 60}[/bold magenta]")
    console.print("[bold magenta]Demo B: Few-Shot — Custom Label Classification[/bold magenta]")
    console.print(
        "[dim]The model doesn't know labels like BILLING_DISPUTE — "
        "examples teach your taxonomy.[/dim]\n"
    )

    ticket_table = Table(show_lines=True)
    ticket_table.add_column("Support Ticket", style="cyan", max_width=55)
    ticket_table.add_column("Category", style="green", max_width=18)

    for ticket in FEW_SHOT_TEST_INPUTS:
        try:
            result = client.classify_ticket_few_shot(ticket)
            ticket_table.add_row(ticket[:55], result)
        except Exception as e:
            logger.error("Few-shot error: %s", e)
            ticket_table.add_row(ticket[:55], "ERROR")

    console.input("\n[dim]Press Enter to continue...[/dim]")
    console.print(ticket_table)

    # --- Demo C: Chain-of-Thought Root Cause ---
    console.print(f"\n[bold magenta]{'═' * 60}[/bold magenta]")
    console.print("[bold magenta]Demo C: Chain-of-Thought — Root Cause Analysis[/bold magenta]")
    console.print("[dim]Comparing zero-shot vs CoT on a bug that requires reasoning.[/dim]\n")
    console.print(Panel(BUG_REPORT, title="Bug Report", border_style="dim"))

    # try:
    #     zero_shot = client.analyze_zero_shot(BUG_REPORT)
    #     console.print(Panel(zero_shot, title="Zero-Shot Analysis", border_style="yellow"))
    # except Exception as e:
    #     logger.error("Zero-shot analysis error: %s", e)

    # console.input("\n[dim]Press Enter to continue...[/dim]")

    try:
        cot = client.analyze_cot(BUG_REPORT)
        console.input("\n[dim]Press Enter to continue...[/dim]")
        console.print(Panel(cot, title="Chain-of-Thought Analysis", border_style="green"))
    except Exception as e:
        logger.error("CoT analysis error: %s", e)

    console.input("\n[dim]Press Enter to continue...[/dim]")
    # --- Summary: When to Use What ---
    console.print(f"\n[bold magenta]{'═' * 60}[/bold magenta]")
    summary = Table(title="When to Use Each Technique", show_lines=True)
    summary.add_column("Technique", style="bold", max_width=14)
    summary.add_column("Best For", style="cyan", max_width=30)
    summary.add_column("Trade-off", style="dim", max_width=30)
    summary.add_row(
        "Zero-Shot",
        "Well-known tasks (sentiment,\ntranslation, summarization)",
        "Fast & cheap, but unreliable\nfor custom taxonomies",
    )
    summary.add_row(
        "Few-Shot",
        "Custom labels, domain-specific\nclassification, style matching",
        "More input tokens, but teaches\nthe model YOUR categories",
    )
    summary.add_row(
        "CoT",
        "Reasoning tasks (debugging,\nmath, root cause analysis)",
        "More output tokens, but better\naccuracy on complex problems",
    )
    console.print(summary)

    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
