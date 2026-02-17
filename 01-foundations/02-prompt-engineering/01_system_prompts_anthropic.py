"""
System Prompts & Role Engineering (Anthropic)

Demonstrates how system prompts control LLM behavior by comparing three configurations:
- Generic assistant (baseline)
- Role-assigned expert
- Role + constraints + output format

All three triage the same support tickets, showing the impact of prompt engineering.
"""

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel

from common import AnthropicTokenTracker, interactive_menu, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# Ambiguous support tickets that force the system prompt to determine interpretation
SUPPORT_TICKETS = [
    {
        "label": "Ticket 1 — Performance complaint",
        "text": (
            "Subject: App is super slow after the update\n\n"
            "Hi, ever since the latest update the app takes forever to load anything. "
            "Pages that used to be instant now hang for 10+ seconds. I'm on Wi-Fi and "
            "everything else works fine. This is really frustrating — I need this for work. "
            "Can you please fix this ASAP?"
        ),
    },
    {
        "label": "Ticket 2 — Feature not working",
        "text": (
            "Subject: Export button doesn't work\n\n"
            "I've been trying to export my report but nothing happens when I click the "
            "export button. I've tried multiple times. I'm using Chrome on Windows. "
            "My colleague says it works for them but I can't figure out what I'm doing wrong. "
            "Is this a known issue?"
        ),
    },
]

TICKET_LABELS = [t["label"] for t in SUPPORT_TICKETS]

# Three system prompt configurations showing progressive refinement
PROMPT_CONFIGS = [
    {
        "label": "A: Generic Assistant",
        "system": "You are a helpful assistant. Help analyze this support ticket.",
    },
    {
        "label": "B: Role-Assigned Expert",
        "system": (
            "You are a senior support engineer at a SaaS company. You've triaged thousands "
            "of tickets. When analyzing tickets, you identify the most likely root cause, "
            "estimate severity, and recommend next steps. You don't hedge — you make a call "
            "based on experience."
        ),
    },
    {
        "label": "C: Role + Constraints + Format",
        "system": (
            "You are a senior support engineer at a SaaS company. You've triaged thousands "
            "of tickets.\n\n"
            "Respond in EXACTLY these sections:\n\n"
            "CATEGORY: Bug / User Error / Feature Request / Configuration\n\n"
            "ROOT CAUSE: One sentence.\n\n"
            "SEVERITY: P1-P4\n\n"
            "NEXT ACTION: One concrete step for the support team.\n\n"
            "Be terse. No explanations beyond what's requested."
        ),
    },
]

CONFIG_LABELS = [c["label"] for c in PROMPT_CONFIGS]


class PromptEngineer:
    """Demonstrates how system prompts shape LLM responses."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker

    def run(self, system_prompt: str, user_prompt: str) -> str:
        """Execute a single LLM call with the given system and user prompts."""
        logger.info("Calling model: %s", self.model)

        response = self.client.messages.create(
            model=self.model,
            temperature=0.1,
            max_tokens=200,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        self.token_tracker.track(response.usage)
        logger.info(
            "Tokens - Input: %d, Output: %d",
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        return str(response.content[0].text)


def main() -> None:
    """Run support ticket triage with three different system prompts."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    engineer = PromptEngineer("claude-sonnet-4-5-20250929", token_tracker)

    header = Panel(
        "[bold cyan]System Prompts & Role Engineering[/bold cyan]\n\n"
        "Comparing 3 system prompt configurations on support ticket triage.\n"
        "Watch how the response style and actionability change with better prompts.",
        title="Prompt Engineering — Anthropic",
    )

    try:
        while True:
            # Step 1: Select a support ticket
            selection = interactive_menu(
                console,
                TICKET_LABELS,
                title="Select a Support Ticket",
                header=header,
                allow_custom=True,
                custom_prompt="Enter a custom support ticket",
            )
            if not selection:
                break

            ticket = next((t for t in SUPPORT_TICKETS if t["label"] == selection), None)
            ticket_text = ticket["text"] if ticket else selection
            ticket_label = ticket["label"] if ticket else "Custom Ticket"
            user_prompt = f"Analyze this support ticket:\n\n{ticket_text}"

            # Step 2: Select prompt configs to run against the ticket
            ticket_header = Panel(
                f"[bold magenta]{ticket_label}[/bold magenta]\n[dim]{ticket_text}[/dim]",
                title="Selected Ticket",
                border_style="magenta",
            )

            while True:
                config_selection = interactive_menu(
                    console,
                    CONFIG_LABELS,
                    title="Select a Prompt Configuration",
                    header=ticket_header,
                )
                if not config_selection:
                    break

                config = next(c for c in PROMPT_CONFIGS if c["label"] == config_selection)

                console.print(f"\n[bold yellow]━━━ {config['label']} ━━━[/bold yellow]")
                console.print(Panel(config["system"], title="System Prompt", border_style="dim"))

                try:
                    response = engineer.run(config["system"], user_prompt)
                    console.print(Panel(response, title=config["label"], border_style="green"))
                except Exception as e:
                    logger.error("Error with config %s: %s", config["label"], e)

                token_tracker.report()
                token_tracker.reset()

                console.print("\n[dim]Press Enter to continue...[/dim]")
                input()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()
