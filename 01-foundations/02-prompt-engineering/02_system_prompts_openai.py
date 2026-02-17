"""
System Prompts & Role Engineering (OpenAI)

Demonstrates how system prompts control LLM behavior by comparing three configurations:
- Generic assistant (baseline)
- Role-assigned expert
- Role + constraints + output format

All three triage the same support tickets, showing the impact of prompt engineering.
"""

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel

from common import OpenAITokenTracker, setup_logging

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
    # {
    #     "label": "Ticket 2 — Feature not working",
    #     "text": (
    #         "Subject: Export button doesn't work\n\n"
    #         "I've been trying to export my report but nothing happens when I click the "
    #         "export button. I've tried multiple times. I'm using Chrome on Windows. "
    #         "My colleague says it works for them but I can't figure out what I'm doing wrong. "
    #         "Is this a known issue?"
    #     ),
    # },
]

# Three system prompt configurations showing progressive refinement
PROMPT_CONFIGS = {
    "A: Generic Assistant": ("You are a helpful assistant. Help analyze this support ticket."),
    "B: Role-Assigned Expert": (
        "You are a senior support engineer at a SaaS company. You've triaged thousands "
        "of tickets. When analyzing tickets, you identify the most likely root cause, "
        "estimate severity, and recommend next steps. You don't hedge — you make a call "
        "based on experience."
    ),
    "C: Role + Constraints + Format": (
        "You are a senior support engineer at a SaaS company. You've triaged thousands "
        "of tickets.\n\n"
        "Respond in EXACTLY these sections:\n\n"
        "CATEGORY: Bug / User Error / Feature Request / Configuration\n\n"
        "ROOT CAUSE: One sentence.\n\n"
        "SEVERITY: P1-P4\n\n"
        "NEXT ACTION: One concrete step for the support team.\n\n"
        "Be terse. No explanations beyond what's requested."
    ),
}


class PromptEngineer:
    """Demonstrates how system prompts shape LLM responses."""

    def __init__(self, model: str, token_tracker: OpenAITokenTracker):
        self.client = OpenAI()
        self.model = model
        self.token_tracker = token_tracker

    def run(self, system_prompt: str, user_prompt: str) -> str:
        """Execute a single LLM call with the given system and user prompts."""
        logger.info("Calling model: %s", self.model)

        # OpenAI uses 'instructions' for the system prompt
        response = self.client.responses.create(
            model=self.model,
            temperature=0.1,
            max_output_tokens=200,
            instructions=system_prompt,
            input=user_prompt,
        )

        if hasattr(response, "usage") and response.usage:
            self.token_tracker.track(response.usage)
            logger.info(
                "Tokens - Input: %d, Output: %d",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

        return response.output_text or ""


def main() -> None:
    """Run support ticket triage with three different system prompts."""
    console = Console()
    token_tracker = OpenAITokenTracker()
    engineer = PromptEngineer("gpt-4.1", token_tracker)

    console.print(
        Panel(
            "[bold cyan]System Prompts & Role Engineering[/bold cyan]\n\n"
            "Comparing 3 system prompt configurations on support ticket triage.\n"
            "Watch how the response style and actionability change with better prompts.",
            title="Prompt Engineering — OpenAI",
        )
    )

    for ticket in SUPPORT_TICKETS:
        console.print(f"\n[bold magenta]{'═' * 60}[/bold magenta]")
        console.print(f"[bold magenta]{ticket['label']}[/bold magenta]")
        console.print(f"[dim]{ticket['text'][:80]}...[/dim]")

        user_prompt = f"Analyze this support ticket:\n\n{ticket['text']}"

        for config_name, system_prompt in PROMPT_CONFIGS.items():
            console.print(f"\n[bold yellow]━━━ {config_name} ━━━[/bold yellow]")
            console.print(f"[dim]System prompt: {system_prompt[:80]}...[/dim]\n")

            try:
                console.input("\n[dim]Press Enter to continue...[/dim]")
                response = engineer.run(system_prompt, user_prompt)
                console.print(Panel(response, title=config_name, border_style="green"))
            except Exception as e:
                logger.error("Error with config %s: %s", config_name, e)


    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
