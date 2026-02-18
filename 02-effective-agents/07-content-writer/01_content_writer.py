"""
Full Agent — "The Content Writer"

Combines ALL patterns from this module into a production content creation pipeline:
- Routing (03): classify content type → type-specific prompts
- Prompt Chaining (02): research → write with type-specific voice
- Orchestrator-Workers (05): dynamic research planning → parallel research
- Parallelization (04): social media fan-out + SEO title voting
- Evaluator-Optimizer (06): write-evaluate-refine loop with quality gate
- Human-in-the-Loop (07): strategic checkpoints at high-leverage decisions
"""

import asyncio
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, interactive_menu, setup_logging
from content_writer import (
    ClassifyDoneEvent,
    ClassifyStartEvent,
    CompleteEvent,
    ContentWriterAgent,
    EvaluateDoneEvent,
    EvaluateStartEvent,
    EvaluationResult,
    HumanCheckpointEvent,
    PlanDoneEvent,
    PlanStartEvent,
    RefineStartEvent,
    ResearchDoneEvent,
    ResearchSectionDoneEvent,
    ResearchStartEvent,
    SeoCandidateEvent,
    SeoDoneEvent,
    SeoResult,
    SeoStartEvent,
    SocialContent,
    SocialDoneEvent,
    SocialStartEvent,
    SocialWriterDoneEvent,
    Source,
    WriteDoneEvent,
    WriteStartEvent,
    WritingResult,
)

load_dotenv(find_dotenv())
logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-20250514"
RESEARCH_MODEL = "claude-haiku-4-5-20251001"
OUTPUT_DIR = Path("output")
SCORE_THRESHOLD = 7.0
MAX_REFINEMENTS = 2

SUGGESTED_TOPICS = [
    "Why Every Backend Team Should Try Feature Flags",
    "How to Build a CLI Tool with Python and Click",
    "What Are Vector Databases and Why Do They Matter",
    "Structured Concurrency Changed How I Think About Async",
]


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _topic_dir(topic: str) -> Path:
    """Create and return a per-topic output directory."""
    slug = topic.lower().replace(" ", "_")[:50]
    path = OUTPUT_DIR / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_artifact(topic: str, filename: str, content: str) -> Path:
    """Save a single artifact file into the topic directory."""
    path = _topic_dir(topic) / filename
    path.write_text(content, encoding="utf-8")
    logger.info("Saved: %s (%d chars)", path, len(content))
    return path


def _save_social(topic: str, social: SocialContent) -> list[Path]:
    """Save each social media artifact as a separate file."""
    paths: list[Path] = []
    for name, content in [
        ("linkedin.md", social.linkedin),
        ("twitter.md", social.twitter),
        ("newsletter.md", social.newsletter),
    ]:
        if content and not content.startswith("Error:"):
            paths.append(_save_artifact(topic, name, content))
    return paths


def _save_seo(topic: str, seo: SeoResult) -> Path:
    """Save SEO voting results."""
    parts = [f"# SEO Title\n\n{seo.winning_title}\n\n"]
    if seo.candidates:
        parts.append("## Candidates\n\n")
        for i, c in enumerate(seo.candidates, 1):
            parts.append(f"{i}. {c}\n")
        parts.append(f"\n## Reasoning\n\n{seo.reasoning}\n")
    return _save_artifact(topic, "seo.md", "".join(parts))


def _display_evaluation(console: Console, evaluation: EvaluationResult, iteration: int) -> None:
    """Display 5-dimension evaluation scores in a Rich table."""
    dimensions = {
        "Clarity": evaluation.clarity,
        "Technical Accuracy": evaluation.technical_accuracy,
        "Structure": evaluation.structure,
        "Engagement": evaluation.engagement,
        "Human Voice": evaluation.human_voice,
    }

    table = Table(title=f"Iteration {iteration} — avg: {evaluation.avg_score:.1f}/10")
    table.add_column("Dimension", style="cyan")
    table.add_column("Score", justify="center")
    for dim, score in dimensions.items():
        color = "green" if score >= 8 else "yellow" if score >= 6 else "red"
        table.add_row(dim, f"[{color}]{score}/10[/{color}]")
    console.print(table)

    if evaluation.issues:
        console.print("[bold red]Issues:[/bold red]")
        for issue in evaluation.issues:
            console.print(f"  [red]•[/red] {issue}")

    if evaluation.suggestions:
        console.print("[bold yellow]Suggestions:[/bold yellow]")
        for suggestion in evaluation.suggestions:
            console.print(f"  [yellow]•[/yellow] {suggestion}")


def _print_path(console: Console, label: str, path: Path) -> None:
    """Print a clickable file link."""
    console.print(f"  [dim]{label}: [link=file://{path.resolve()}]{path}[/link][/dim]")


def _show_sources(console: Console, sources: list[Source]) -> None:
    """Display web search sources as clickable links in a panel."""
    if not sources:
        return
    lines = [f"  [dim]•[/dim] [link={s.url}]{s.title}[/link]" for s in sources]
    console.print(Panel("\n".join(lines), title="Sources", border_style="dim"))


def _human_checkpoint(console: Console, event: HumanCheckpointEvent) -> tuple[bool, str]:
    """Pause for human review at a strategic decision point."""
    console.print(
        Panel(event.content, title=f"Checkpoint: {event.title}", border_style="bright_magenta")
    )
    console.print(f"\n[bold magenta]{event.question}[/bold magenta]")
    console.print("[dim](y)es / (n)o with feedback[/dim]")
    console.print("[bold magenta]> [/bold magenta]", end="")

    response = input().strip().lower()
    if response in ["y", "yes", ""]:
        return True, ""

    console.print("[dim]Feedback:[/dim] ", end="")
    feedback = input().strip() if response == "n" else response
    return False, feedback


# ─── Event Consumer ──────────────────────────────────────────────────────────


async def _run_with_events(
    agent: ContentWriterAgent,
    topic: str,
    console: Console,
    tracker: AnthropicTokenTracker,
) -> WritingResult | None:
    """Consume typed events from the agent and render with Rich."""
    state: dict[str, Path | None] = {"last_draft_path": None}

    def on_checkpoint(event: HumanCheckpointEvent) -> tuple[bool, str]:
        draft_path = state["last_draft_path"]
        if draft_path and event.checkpoint_id == "final_review":
            _print_path(console, "Latest draft", draft_path)
        return _human_checkpoint(console, event)

    result: WritingResult | None = None

    async for event in agent.run_stream(
        topic,
        score_threshold=SCORE_THRESHOLD,
        max_refinements=MAX_REFINEMENTS,
        on_human_checkpoint=on_checkpoint,
    ):
        match event:
            # Phase 1: Classification
            case ClassifyStartEvent():
                console.print("\n[bold yellow]Phase 1:[/bold yellow] Classifying content type...")

            case ClassifyDoneEvent(classification=c):
                console.print(f"  [green]✓[/green] {c.content_type.value}: {c.topic}")
                tracker.report()

            # Phase 2: Research planning
            case PlanStartEvent():
                console.print("\n[bold yellow]Phase 2:[/bold yellow] Planning research...")

            case PlanDoneEvent(subtopics=subs):
                for i, s in enumerate(subs, 1):
                    console.print(f"  {i}. [bold]{s.title}[/bold]")
                tracker.report()

            # Phase 3: Parallel research
            case ResearchStartEvent(count=n):
                console.print(
                    f"\n[bold yellow]Phase 3:[/bold yellow] "
                    f"Researching {n} subtopics in parallel..."
                )

            case ResearchSectionDoneEvent(title=t, sources=srcs):
                console.print(f"  [green]✓[/green] {t}")
                _show_sources(console, srcs)

            case ResearchDoneEvent():
                tracker.report()

            # Phase 4: Write
            case WriteStartEvent(iteration=i):
                label = "Writing" if i == 1 else f"Rewriting (round {i - 1})"
                console.print(f"\n[bold yellow]Phase 4:[/bold yellow] {label}...")

            case WriteDoneEvent(iteration=i, content_length=length, content=draft, sources=srcs):
                path = _save_artifact(topic, f"draft_v{i}.md", draft)
                state["last_draft_path"] = path
                console.print(
                    f"  [green]✓[/green] v{i}: {length:,} chars — "
                    f"[dim][link=file://{path.resolve()}]{path}[/link][/dim]"
                )
                _show_sources(console, srcs)

            # Phase 5: Evaluate + refine
            case EvaluateStartEvent(iteration=i):
                console.print(f"\n[bold yellow]Phase 5:[/bold yellow] Evaluating (round {i})...")

            case EvaluateDoneEvent(iteration=i, evaluation=e):
                _display_evaluation(console, e, i)
                tracker.report()

                if e.avg_score >= SCORE_THRESHOLD:
                    console.print(
                        f"\n[green]Score {e.avg_score:.1f} >= {SCORE_THRESHOLD}"
                        f" — quality met![/green]"
                    )
                else:
                    console.print(f"\n[yellow]Score {e.avg_score:.1f} < {SCORE_THRESHOLD}[/yellow]")

            case RefineStartEvent(iteration=i):
                console.print(f"\n[yellow]Refining (round {i - 1}/{MAX_REFINEMENTS})...[/yellow]")

            # Phase 6: Social media
            case SocialStartEvent():
                console.print(
                    "\n[bold yellow]Phase 6:[/bold yellow] Social media blast (fan-out)..."
                )

            case SocialWriterDoneEvent(name=n):
                console.print(f"  [green]✓[/green] {n}")

            case SocialDoneEvent(social=s):
                tracker.report()
                paths = _save_social(topic, s)
                for p in paths:
                    _print_path(console, p.stem, p)
                for key, content in [
                    ("LINKEDIN", s.linkedin),
                    ("TWITTER", s.twitter),
                    ("NEWSLETTER", s.newsletter),
                ]:
                    if content and not content.startswith("Error:"):
                        console.print(Panel(Markdown(content), title=key, border_style="cyan"))

            # Phase 7: SEO title voting
            case SeoStartEvent():
                console.print("\n[bold yellow]Phase 7:[/bold yellow] SEO title voting...")

            case SeoCandidateEvent(title=t):
                console.print(f"  [dim]• {t}[/dim]")

            case SeoDoneEvent(seo=s):
                console.print(f"  [green]✓[/green] Winner: {s.winning_title}")
                console.print(f"  [dim]{s.reasoning}[/dim]")
                tracker.report()
                path = _save_seo(topic, s)
                _print_path(console, "seo", path)

            # Pipeline complete
            case CompleteEvent(result=r):
                result = r

    return result


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    """Run the full content writer agent."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    agent = ContentWriterAgent(MODEL, RESEARCH_MODEL, token_tracker)

    header = Panel(
        "[bold cyan]Full Agent — The Content Writer[/bold cyan]\n\n"
        "Combines ALL patterns from this module into one pipeline:\n"
        "  [Classify] → [Plan] → [Research] → [Write] → [Evaluate] → [Refine]\n"
        "  → [Human Review] → [Social Media Blast] → [SEO Title Voting]\n\n"
        "Patterns:\n"
        "  Routing (03) | Prompt Chaining (02) | Parallelization (04)\n"
        "  Orchestrator-Workers (05) | Evaluator-Optimizer (06) | Human-in-the-Loop (07)",
        title="Content Writer",
    )

    async def async_main() -> None:
        while True:
            topic = interactive_menu(
                console,
                SUGGESTED_TOPICS,
                title="Select a Topic",
                header=header,
                allow_custom=True,
                custom_prompt="Enter your topic",
            )
            if not topic:
                break

            console.print(f"\n[bold green]Topic:[/bold green] {topic}")

            try:
                result = await _run_with_events(agent, topic, console, token_tracker)

                if result:
                    # Save final article
                    article_path = _save_artifact(topic, "article.md", result.content)
                    _print_path(console, "Final article", article_path)

                    # Show final article
                    console.print("\n[bold blue]Final Article:[/bold blue]")
                    console.print(Markdown(result.content))

                    # Show output directory
                    topic_dir = _topic_dir(topic)
                    console.print(
                        f"\n[dim]All artifacts: "
                        f"[link=file://{topic_dir.resolve()}]{topic_dir}/[/link][/dim]"
                    )

                console.print("\n[dim]Press Enter to continue...[/dim]")
                input()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error("Pipeline failed: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")
            finally:
                token_tracker.report()
                token_tracker.reset()

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        os._exit(130)


if __name__ == "__main__":
    main()
