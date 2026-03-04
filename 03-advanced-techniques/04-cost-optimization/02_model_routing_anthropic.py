"""
Model Routing (Anthropic)

Demonstrates cost optimization through intelligent model routing. A cheap
classifier (Haiku) evaluates task difficulty and routes to Haiku (easy) or
Sonnet (hard). Shows actual cost savings vs an all-Sonnet baseline.
"""

from dataclasses import dataclass, field

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, setup_logging
from common.menu import interactive_menu

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

# Model configuration
MODEL_CLASSIFIER = "claude-haiku-4-5-20251001"
MODEL_EASY = "claude-haiku-4-5-20251001"
MODEL_HARD = "claude-sonnet-4-5-20250929"

# Pricing ($ per million tokens)
PRICING = {
    "haiku_input": 1.00,
    "haiku_output": 5.00,
    "sonnet_input": 3.00,
    "sonnet_output": 15.00,
}

# Sample tasks mixing easy and hard
SAMPLE_TASKS = [
    "What is the capital of France?",
    "Convert 72 degrees Fahrenheit to Celsius.",
    "Design a microservices architecture for a real-time multiplayer game that needs to handle "
    "100,000 concurrent users with sub-50ms latency.",
    "What year did the first iPhone launch?",
    "Analyze the trade-offs between event sourcing and traditional CRUD for a financial "
    "transaction system that requires full audit trails and regulatory compliance.",
    "How many meters are in a kilometer?",
    "Compare and contrast the CAP theorem implications when choosing between PostgreSQL, "
    "Cassandra, and CockroachDB for a globally distributed e-commerce platform.",
    "What is the chemical symbol for gold?",
]


@dataclass
class TaskResult:
    """Result of a routed task execution."""

    task: str
    difficulty: str
    model_used: str
    response: str
    routed_cost: float
    baseline_cost: float  # what it would cost on Sonnet


class ModelRouter:
    """Routes tasks to appropriate models based on complexity."""

    def __init__(self, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.token_tracker = token_tracker
        self.results: list[TaskResult] = field(default_factory=list)
        self.results = []

    def classify(self, task: str) -> str:
        """Use Haiku to classify task difficulty as 'easy' or 'hard'."""
        response = self.client.messages.create(
            model=MODEL_CLASSIFIER,
            max_tokens=10,
            system=(
                "Classify the following task as either 'easy' or 'hard'.\n"
                "Easy: simple factual lookups, unit conversions, basic math, definitions.\n"
                "Hard: analysis, architecture design, multi-step reasoning, comparisons, "
                "creative writing, code review.\n"
                "Respond with exactly one word: easy or hard."
            ),
            messages=[{"role": "user", "content": task}],
        )
        self.token_tracker.track(response.usage)

        classification = str(response.content[0].text).strip().lower()
        # Default to hard if classification is unclear
        if classification not in ("easy", "hard"):
            logger.warning("Unclear classification '%s', defaulting to hard", classification)
            classification = "hard"

        logger.info("Classified as '%s': %s", classification, task[:60])
        return classification

    def execute(self, task: str, model: str) -> tuple[str, int, int]:
        """Run task on specified model, return (response, input_tokens, output_tokens)."""
        response = self.client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": task}],
        )
        self.token_tracker.track(response.usage)

        return (
            str(response.content[0].text),
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a given model and token counts."""
        if model == MODEL_HARD:
            return (
                input_tokens * PRICING["sonnet_input"] + output_tokens * PRICING["sonnet_output"]
            ) / 1_000_000
        return (
            input_tokens * PRICING["haiku_input"] + output_tokens * PRICING["haiku_output"]
        ) / 1_000_000

    def route_and_execute(self, task: str) -> TaskResult:
        """Classify, route, execute, and track costs."""
        difficulty = self.classify(task)

        model = MODEL_EASY if difficulty == "easy" else MODEL_HARD
        response_text, input_tokens, output_tokens = self.execute(task, model)

        routed_cost = self._calculate_cost(model, input_tokens, output_tokens)
        baseline_cost = self._calculate_cost(MODEL_HARD, input_tokens, output_tokens)

        result = TaskResult(
            task=task,
            difficulty=difficulty,
            model_used=model,
            response=response_text,
            routed_cost=routed_cost,
            baseline_cost=baseline_cost,
        )
        self.results.append(result)

        return result

    def get_summary(self) -> dict:
        """Aggregate cost comparison across all results."""
        total_routed = sum(r.routed_cost for r in self.results)
        total_baseline = sum(r.baseline_cost for r in self.results)
        savings = total_baseline - total_routed
        savings_pct = (savings / total_baseline * 100) if total_baseline > 0 else 0
        easy_count = sum(1 for r in self.results if r.difficulty == "easy")
        hard_count = sum(1 for r in self.results if r.difficulty == "hard")

        return {
            "total_tasks": len(self.results),
            "easy_count": easy_count,
            "hard_count": hard_count,
            "total_routed_cost": total_routed,
            "total_baseline_cost": total_baseline,
            "savings": savings,
            "savings_pct": savings_pct,
        }


def _render_task_result(console: Console, result: TaskResult, index: int) -> None:
    """Render a single task result with routing info."""
    model_label = "Haiku" if result.model_used == MODEL_EASY else "Sonnet"
    diff_color = "green" if result.difficulty == "easy" else "yellow"
    savings = result.baseline_cost - result.routed_cost
    savings_pct = (savings / result.baseline_cost * 100) if result.baseline_cost > 0 else 0

    console.print(
        Panel(
            f"[dim]Task:[/dim] {result.task}\n"
            f"[dim]Difficulty:[/dim] [{diff_color}]{result.difficulty}[/{diff_color}] → "
            f"[bold]{model_label}[/bold]\n"
            f"[dim]Routed cost:[/dim] [green]${result.routed_cost:.6f}[/green]  "
            f"[dim]Baseline (Sonnet):[/dim] [red]${result.baseline_cost:.6f}[/red]  "
            f"[dim]Saved:[/dim] [bold green]${savings:.6f} ({savings_pct:.0f}%)[/bold green]",
            title=f"Task {index}",
            border_style="dim",
            padding=(0, 1),
        )
    )


def _render_summary(console: Console, summary: dict) -> None:
    """Render aggregate cost summary."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Metric", style="dim", min_width=22)
    table.add_column("Value", justify="right")

    table.add_row("Tasks processed", f"[cyan]{summary['total_tasks']}[/cyan]")
    table.add_row(
        "Routing breakdown",
        f"[green]{summary['easy_count']} easy[/green] / "
        f"[yellow]{summary['hard_count']} hard[/yellow]",
    )
    table.add_row(
        "Cost (routed)",
        f"[green]${summary['total_routed_cost']:.6f}[/green]",
    )
    table.add_row(
        "Cost (all-Sonnet baseline)",
        f"[red]${summary['total_baseline_cost']:.6f}[/red]",
    )
    table.add_row(
        "Total savings",
        f"[bold green]${summary['savings']:.6f} ({summary['savings_pct']:.1f}%)[/bold green]",
    )

    console.print(
        Panel(
            table,
            title="Cost Summary — Routed vs All-Sonnet",
            border_style="green",
            padding=(0, 1),
        )
    )


def _run_demo(console: Console, router: ModelRouter) -> None:
    """Run all sample tasks and show results."""
    console.print(f"\n[bold]Running {len(SAMPLE_TASKS)} sample tasks...[/bold]\n")

    for i, task in enumerate(SAMPLE_TASKS, 1):
        console.print(f"[dim]Processing task {i}/{len(SAMPLE_TASKS)}...[/dim]")
        try:
            result = router.route_and_execute(task)
            _render_task_result(console, result, i)
            # Show truncated response
            preview = (
                result.response[:200] + "..." if len(result.response) > 200 else result.response
            )
            console.print(Markdown(preview))
            console.print()
        except Exception as e:
            logger.error("Error processing task %d: %s", i, e)
            console.print(f"[red]Error: {e}[/red]\n")

    _render_summary(console, router.get_summary())


def _run_interactive(console: Console, router: ModelRouter) -> None:
    """Interactive mode — user enters tasks, sees classification in real-time."""
    console.print(
        "\n[bold]Interactive mode[/bold] — enter tasks to see routing decisions.\n"
        "Type [bold]'summary'[/bold] for cost totals, [bold]'quit'[/bold] to exit.\n"
    )

    while True:
        console.print("[bold green]Task:[/bold green] ", end="")
        user_input = input().strip()

        if user_input.lower() in ["quit", "exit", ""]:
            break

        if user_input.lower() == "summary":
            if router.results:
                _render_summary(console, router.get_summary())
            else:
                console.print("[dim]No tasks processed yet.[/dim]")
            continue

        try:
            result = router.route_and_execute(user_input)
            _render_task_result(console, result, len(router.results))

            console.print("\n[bold blue]Response:[/bold blue]")
            console.print(Markdown(result.response))
            console.print()

        except Exception as e:
            logger.error("Error processing task: %s", e)
            console.print(f"\n[red]Error: {e}[/red]")

    if router.results:
        _render_summary(console, router.get_summary())


def main() -> None:
    """Main orchestration function for the model routing demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    router = ModelRouter(token_tracker)

    header = Panel(
        "[bold cyan]Model Routing Demo[/bold cyan]\n\n"
        "A cheap classifier (Haiku) evaluates each task's difficulty,\n"
        "then routes to [green]Haiku[/green] (easy) or [yellow]Sonnet[/yellow] (hard).\n\n"
        "Haiku costs ~73% less than Sonnet for input — routing simple tasks\n"
        "to the cheaper model saves real money at scale.\n\n"
        "[bold]Pricing:[/bold]\n"
        f"  Haiku:  ${PRICING['haiku_input']:.2f} input / ${PRICING['haiku_output']:.2f} output  (per MTok)\n"
        f"  Sonnet: ${PRICING['sonnet_input']:.2f} input / ${PRICING['sonnet_output']:.2f} output (per MTok)",
        title="Smart Model Routing",
    )

    mode = interactive_menu(
        console,
        items=[
            "Demo — run sample tasks with auto-routing",
            "Interactive — enter your own tasks",
        ],
        title="Select Mode",
        header=header,
    )

    if mode is None:
        return

    if mode.startswith("Demo"):
        _run_demo(console, router)
    else:
        _run_interactive(console, router)

    # Final token report
    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
