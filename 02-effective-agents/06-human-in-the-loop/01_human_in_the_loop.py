"""
Human-in-the-Loop — "The Approval Gate"

Demonstrates pausing an agentic workflow at strategic checkpoints for human review.
The LLM drafts an email, a human approves or rejects with feedback, and the LLM
revises — showing where human oversight adds the most value.
"""

from collections.abc import Callable
from typing import cast

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel

from common import AnthropicTokenTracker, interactive_menu, setup_logging

load_dotenv(find_dotenv())
logger = setup_logging(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_REVISIONS = 2

SUGGESTED_SCENARIOS = [
    "Decline a job offer politely — grateful but chose another opportunity",
    "Ask your team to work overtime this weekend — critical deadline, apologetic tone",
    "Request a meeting with a VP to discuss budget — formal, data-driven",
    "Follow up on an unanswered proposal — persistent but respectful",
]

# --- Prompts ---

SYSTEM_PROMPT = (
    "You are a professional email writer. Write clear, concise emails that match "
    "the requested tone. Output only the email — subject line, then body. "
    "No meta-commentary. Keep it under 300 words."
)

REVISE_SYSTEM_PROMPT = (
    "You are a professional email writer. Revise the email based on the feedback provided. "
    "Return only the revised email — subject line, then body. No explanation of changes."
)

# Checkpoint function type: (title, content, question) -> (approved, feedback)
CheckpointFn = Callable[[str, str, str], tuple[bool, str]]


class EmailDrafter:
    """Draft and revise emails with human checkpoints."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker) -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker

    def _call_llm(self, system: str, user_msg: str, *, max_tokens: int = 1024) -> str:
        """Make an LLM call and return text response."""
        logger.info("Calling %s", self.model)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        self.token_tracker.track(response.usage)
        return cast(str, response.content[0].text)

    def _draft(self, scenario: str) -> str:
        """Generate an initial email draft from a scenario description."""
        return self._call_llm(SYSTEM_PROMPT, f"Write an email for this scenario: {scenario}")

    def _revise(self, draft: str, feedback: str) -> str:
        """Revise a draft based on human feedback."""
        user_msg = f"Original email:\n{draft}\n\nFeedback to address:\n{feedback}"
        return self._call_llm(REVISE_SYSTEM_PROMPT, user_msg)

    def run(self, scenario: str, *, checkpoint_fn: CheckpointFn | None = None) -> str:
        """Draft an email with human checkpoints for review."""
        check = checkpoint_fn or (lambda _t, _c, _q: (True, ""))

        # Step 1: Generate initial draft
        logger.info("Generating draft for: %s", scenario)
        draft = self._draft(scenario)
        self.token_tracker.report()

        # === Checkpoint 1: Draft review (high-leverage — catches wrong direction early) ===
        approved, feedback = check(
            "Draft Review",
            draft,
            "Does this email look right? Approve to finalize, or reject with feedback.",
        )

        if approved and not feedback:
            return draft
        # Edit mode: human provided replacement text
        if approved and feedback:
            return feedback

        # Rejected: enter revision loop
        for revision in range(1, MAX_REVISIONS + 1):
            logger.info("Revising draft (round %d/%d)", revision, MAX_REVISIONS)
            draft = self._revise(draft, feedback)
            self.token_tracker.report()

            # === Checkpoint 2: Revision review ===
            approved, feedback = check(
                f"Revision Review ({revision}/{MAX_REVISIONS})",
                draft,
                "Better? Approve to finalize, or reject with more feedback.",
            )

            if approved and not feedback:
                return draft
            if approved and feedback:
                return feedback

        logger.info("Max revisions reached, returning last draft")
        return draft


def human_checkpoint(console: Console, title: str, content: str, question: str) -> tuple[bool, str]:
    """Pause for human review. Returns (approved, feedback)."""
    console.print(Panel(content, title=f"Checkpoint: {title}", border_style="bright_magenta"))
    console.print(f"\n[bold magenta]{question}[/bold magenta]")
    console.print("[dim](y)es / (n)o with feedback / (e)dit to provide replacement[/dim]")
    console.print("[bold magenta]> [/bold magenta]", end="")

    response = input().strip().lower()

    if response in ("y", "yes", ""):
        return True, ""
    elif response.startswith("e"):
        console.print("[dim]Enter replacement (Enter twice to finish):[/dim]")
        lines: list[str] = []
        empty = 0
        while empty < 1:
            line = input()
            if line.strip() == "":
                empty += 1
            else:
                empty = 0
                lines.append(line)
        return True, "\n".join(lines)
    else:
        console.print("[dim]Enter feedback:[/dim] ", end="")
        feedback = input().strip()
        return False, feedback


def main() -> None:
    """Run the human-in-the-loop email drafting demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()

    def checkpoint_fn(title: str, content: str, question: str) -> tuple[bool, str]:
        return human_checkpoint(console, title, content, question)

    header = Panel(
        "[bold cyan]Human-in-the-Loop — The Approval Gate[/bold cyan]\n\n"
        "LLM drafts an email → you review at checkpoints:\n"
        "1. After draft — right tone and content?\n"
        "2. After revision — feedback addressed?\n\n"
        "Options: (y)es approve, (n)o + feedback, (e)dit replacement\n"
        f"Max {MAX_REVISIONS} revisions per email.",
        title="Human-in-the-Loop",
    )

    try:
        while True:
            scenario = interactive_menu(
                console,
                SUGGESTED_SCENARIOS,
                title="Select an Email Scenario",
                header=header,
                allow_custom=True,
                custom_prompt="Describe your email scenario",
            )
            if not scenario:
                break

            console.print(f"\n[bold green]Scenario:[/bold green] {scenario}")
            drafter = EmailDrafter(MODEL, token_tracker)

            try:
                result = drafter.run(scenario, checkpoint_fn=checkpoint_fn)

                console.print("\n[bold blue]Final Email:[/bold blue]")
                console.print(Panel(result, border_style="green"))

                console.print("\n[dim]Press Enter to continue...[/dim]")
                input()
            except Exception as e:
                logger.error("Email drafting failed: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")
            finally:
                token_tracker.reset()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()
