"""
Few-Shot & Chain-of-Thought Prompting (Anthropic)

Demonstrates three prompting techniques, each on a task where it shines:
1. Zero-shot — sentiment analysis (well-understood task, no examples needed)
2. Few-shot — classification with custom domain labels (teaches YOUR taxonomy)
3. Chain-of-thought — root cause analysis (multi-step reasoning needed)

Each demo shows WHY you'd pick that technique over the others.
"""

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, interactive_menu, setup_logging

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

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker

    def _call(self, system_prompt: str, user_content: str, max_tokens: int = 256) -> str:
        """Make a single API call and track tokens."""
        response = self.client.messages.create(
            model=self.model,
            temperature=0.0,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        self.token_tracker.track(response.usage)
        return str(response.content[0].text).strip()

    # --- Zero-Shot ---
    def classify_sentiment(self, review: str) -> str:
        """Classify sentiment with no examples — the model already understands this task."""
        system = (
            "Classify the sentiment of the following product review.\n"
            "Respond with exactly one word: POSITIVE, NEGATIVE, or NEUTRAL."
        )
        return self._call(system, review)

    # --- Few-Shot ---
    def classify_ticket_few_shot(self, ticket: str) -> str:
        """Classify with domain-specific labels the model wouldn't know without examples."""
        examples = "\n".join(
            f'Ticket: "{text}"\nCategory: {label}' for text, label in FEW_SHOT_EXAMPLES
        )
        system = (
            "Classify support tickets into one of these categories: "
            "BILLING_DISPUTE, ACCOUNT_ACCESS, TECHNICAL_BUG, FEATURE_REQUEST\n\n"
            f"Examples:\n\n{examples}\n\n"
            "Respond with ONLY the category name."
        )
        return self._call(system, f'Ticket: "{ticket}"\nCategory:')

    # --- Chain-of-Thought ---
    def analyze_zero_shot(self, bug_report: str) -> str:
        """Analyze a bug report without reasoning guidance — baseline."""
        system = (
            "You are a senior engineer. Identify the most likely root cause of this bug.\n"
            "Be concise — one or two sentences."
        )
        return self._call(system, bug_report)

    def analyze_cot(self, bug_report: str) -> str:
        """Analyze with chain-of-thought — reason through the problem step by step."""
        system = (
            "You are a senior engineer. Analyze this bug report step by step:\n"
            "1. What patterns do you observe? (timing, scope, triggers)\n"
            "2. What does each clue rule in or rule out?\n"
            "3. What is the most likely root cause?\n"
            "4. What would you check first to confirm?\n\n"
            "Think through each step before concluding."
        )
        return self._call(system, bug_report, max_tokens=512)


DEMO_LABELS = [
    "A: Zero-Shot — Sentiment Analysis",
    "B: Few-Shot — Custom Label Classification",
    "C: Chain-of-Thought — Root Cause Analysis",
]


ZERO_SHOT_SYSTEM = (
    "Classify the sentiment of the following product review.\n"
    "Respond with exactly one word: POSITIVE, NEGATIVE, or NEUTRAL."
)

FEW_SHOT_SYSTEM_TEMPLATE = (
    "Classify support tickets into one of these categories: "
    "BILLING_DISPUTE, ACCOUNT_ACCESS, TECHNICAL_BUG, FEATURE_REQUEST\n\n"
    "Examples:\n\n{examples}\n\n"
    "Respond with ONLY the category name."
)

COT_SYSTEM = (
    "You are a senior engineer. Analyze this bug report step by step:\n"
    "1. What patterns do you observe? (timing, scope, triggers)\n"
    "2. What does each clue rule in or rule out?\n"
    "3. What is the most likely root cause?\n"
    "4. What would you check first to confirm?\n\n"
    "Think through each step before concluding."
)


def _run_zero_shot(console: Console, client: PromptingClient) -> None:
    """Run the zero-shot sentiment analysis demo."""
    console.print("[dim]No examples needed — the model already understands sentiment.[/dim]\n")
    console.print(Panel(ZERO_SHOT_SYSTEM, title="System Prompt", border_style="dim"))

    sentiment_table = Table(show_lines=True)
    sentiment_table.add_column("Review", style="cyan", max_width=55)
    sentiment_table.add_column("Sentiment", style="green", max_width=12)

    for review in REVIEWS:
        try:
            result = client.classify_sentiment(review)
            sentiment_table.add_row(review, result)
        except Exception as e:
            logger.error("Sentiment error: %s", e)
            sentiment_table.add_row(review, "ERROR")

    console.print(sentiment_table)


def _run_few_shot(console: Console, client: PromptingClient) -> None:
    """Run the few-shot custom label classification demo."""
    console.print(
        "[dim]The model doesn't know labels like BILLING_DISPUTE — "
        "examples teach your taxonomy.[/dim]\n"
    )
    examples = "\n".join(
        f'Ticket: "{text}"\nCategory: {label}' for text, label in FEW_SHOT_EXAMPLES
    )
    system_prompt = FEW_SHOT_SYSTEM_TEMPLATE.format(examples=examples)
    console.print(Panel(system_prompt, title="System Prompt", border_style="dim"))

    ticket_table = Table(show_lines=True)
    ticket_table.add_column("Support Ticket", style="cyan", max_width=55)
    ticket_table.add_column("Category", style="green", max_width=18)

    for ticket in FEW_SHOT_TEST_INPUTS:
        try:
            result = client.classify_ticket_few_shot(ticket)
            ticket_table.add_row(ticket, result)
        except Exception as e:
            logger.error("Few-shot error: %s", e)
            ticket_table.add_row(ticket, "ERROR")

    console.print(ticket_table)


def _run_cot(console: Console, client: PromptingClient) -> None:
    """Run the chain-of-thought root cause analysis demo."""
    console.print("[dim]CoT on a bug report that requires multi-step reasoning.[/dim]\n")
    console.print(Panel(COT_SYSTEM, title="System Prompt", border_style="dim"))
    console.print(Panel(BUG_REPORT, title="User Message", border_style="dim"))

    try:
        cot = client.analyze_cot(BUG_REPORT)
        console.print(Panel(cot, title="Chain-of-Thought Analysis", border_style="green"))
    except Exception as e:
        logger.error("CoT analysis error: %s", e)


def main() -> None:
    """Run three demos showing when to use each prompting technique."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    client = PromptingClient("claude-sonnet-4-6", token_tracker)

    header = Panel(
        "[bold cyan]Few-Shot & Chain-of-Thought Prompting[/bold cyan]\n\n"
        "Three demos, each using the technique where it shines:\n"
        "  A. Zero-shot — sentiment analysis (task the model already knows)\n"
        "  B. Few-shot — custom label classification (teaching YOUR taxonomy)\n"
        "  C. Chain-of-thought — root cause analysis (multi-step reasoning)",
        title="Prompt Engineering — Anthropic",
    )

    demos = {
        DEMO_LABELS[0]: _run_zero_shot,
        DEMO_LABELS[1]: _run_few_shot,
        DEMO_LABELS[2]: _run_cot,
    }

    try:
        while True:
            selection = interactive_menu(
                console,
                DEMO_LABELS,
                title="Select a Demo",
                header=header,
            )
            if not selection:
                break

            console.print(f"\n[bold yellow]━━━ {selection} ━━━[/bold yellow]")

            try:
                demos[selection](console, client)
            except Exception as e:
                logger.error("Demo error: %s", e)

            token_tracker.report()
            token_tracker.reset()

            console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()
