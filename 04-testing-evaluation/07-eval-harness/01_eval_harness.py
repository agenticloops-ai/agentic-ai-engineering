"""
Eval Harness — Capstone

Complete evaluation pipeline combining unit testing patterns, evals, tracing,
red teaming, and benchmarking into a unified harness for a research assistant agent.

This capstone integrates all five techniques from Module 05:
1. Testable agent design with dependency injection
2. Golden datasets with code-based and composite grading
3. Execution tracing linked to eval results
4. Adversarial safety testing suite
5. Model benchmarking with Pareto analysis

Supports two modes:
- Simulated (default): pre-defined responses, no API calls, instant results
- Live: real Anthropic API calls with tool-use agent loop
"""

import json
import os
from pathlib import Path
from typing import Any

from common import AnthropicTokenTracker, interactive_menu, setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel

from eval_harness import (
    BenchmarkRunner,
    CompositeGrader,
    EvalReport,
    EvalResult,
    EvalTask,
    EvalTrial,
    ResearchAgent,
    SafetyTester,
    SimulatedResearchAgent,
)
from eval_harness.red_team import load_adversarial_tasks
from eval_harness.reporter import EvalReporter
from eval_harness.tracer import SimpleTracer

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


MODE_OPTIONS = [
    "Simulated — pre-defined responses, no API calls",
    "Live — real Anthropic API calls",
]

AVAILABLE_MODELS = [
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-0-20250514",
]


def select_mode_and_create_agent(console: Console, header: Panel) -> Any:
    """Interactive mode and model selection, returns the configured agent."""
    mode = interactive_menu(console, MODE_OPTIONS, title="Select Run Mode", header=header)
    if mode is None:
        raise SystemExit(0)

    if mode.startswith("Live"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            console.print("[red bold]Live mode requires ANTHROPIC_API_KEY to be set[/red bold]")
            raise SystemExit(1)

        model = interactive_menu(console, AVAILABLE_MODELS, title="Select Model", header=header)
        if model is None:
            raise SystemExit(0)

        import anthropic

        client = anthropic.Anthropic()
        console.print(
            f"\n[green bold]Running in LIVE mode[/green bold] — real API calls to {model}\n"
            "[dim]Eval trials and safety tests use the live agent. "
            "Benchmarks remain simulated (multi-model comparison).[/dim]\n"
        )
        return ResearchAgent(client=client, model=model)

    console.print("\n[dim]Running in SIMULATED mode — pre-defined responses, no API calls.[/dim]\n")
    return SimulatedResearchAgent()


def load_golden_tasks(path: Path) -> list[EvalTask]:
    """Load evaluation tasks from a golden dataset JSON file."""
    with Path.open(path, encoding="utf-8") as f:
        data = json.load(f)
    tasks = [EvalTask(**t) for t in data["tasks"]]
    logger.info("Loaded %d golden tasks (v%s)", len(tasks), data["version"])
    return tasks


def run_eval_trials(
    agent: ResearchAgent | SimulatedResearchAgent,
    tasks: list[EvalTask],
    tracer: SimpleTracer,
) -> list[EvalTrial]:
    """Run the agent on each task and collect trials with tracing."""
    trials: list[EvalTrial] = []

    for task in tasks:
        question_preview = task.question[:50] + "…" if len(task.question) > 50 else task.question
        logger.info("Evaluating task %s: %s", task.id, question_preview)

        # Trace the eval execution
        span = tracer.start_span(f"eval_{task.id}", "eval_trial")

        response = agent.answer(task.question, task_id=task.id)

        tracer.end_span(span)

        trial = EvalTrial(
            task_id=task.id,
            answer=response["answer"],
            tool_calls=response.get("tool_calls", []),
            trace=tracer.get_spans()[-1:],
            latency_ms=response.get("latency_ms", 0.0),
            input_tokens=response.get("input_tokens", 0),
            output_tokens=response.get("output_tokens", 0),
        )
        trials.append(trial)

    return trials


def grade_trials(
    trials: list[EvalTrial],
    tasks: list[EvalTask],
    grader: CompositeGrader,
) -> list[EvalResult]:
    """Grade all trials and produce eval results."""
    task_map = {t.id: t for t in tasks}
    results: list[EvalResult] = []

    for trial in trials:
        task = task_map[trial.task_id]
        scores = grader.grade(trial, task)

        # Pass rate based on composite score
        composite = next((s for s in scores if s.grader_name == "composite"), None)
        pass_rate = 1.0 if (composite and composite.passed) else 0.0
        avg_score = composite.score if composite else 0.0

        result = EvalResult(
            task_id=trial.task_id,
            trials=[trial],
            grader_scores=scores,
            pass_rate=pass_rate,
            avg_score=avg_score,
        )
        results.append(result)

    return results


def main() -> None:
    """Run the full evaluation pipeline."""
    console = Console()
    token_tracker = AnthropicTokenTracker()

    header = Panel(
        "[bold cyan]Eval Harness — Capstone[/bold cyan]\n\n"
        "Complete evaluation pipeline combining:\n"
        "  1. Testable agent design (dependency injection)\n"
        "  2. Golden dataset evals (keyword + citation grading)\n"
        "  3. Execution tracing (spans linked to results)\n"
        "  4. Adversarial safety testing (red team suite)\n"
        "  5. Model benchmarking (Pareto analysis)",
        title="Tutorial 06",
    )

    # Interactive mode and model selection
    agent = select_mode_and_create_agent(console, header)

    # Step 1: Load datasets
    base_dir = Path(__file__).parent
    tasks = load_golden_tasks(base_dir / "datasets" / "golden_tasks.json")
    adversarial_attacks = load_adversarial_tasks(base_dir / "datasets" / "adversarial_tasks.json")
    console.print(
        f"[bold]Step 1:[/bold] Loaded {len(tasks)} tasks, {len(adversarial_attacks)} attacks\n"
    )

    # Step 2: Initialize components
    tracer = SimpleTracer()
    grader = CompositeGrader(keyword_weight=0.5, citation_weight=0.5)
    console.print("[bold]Step 2:[/bold] Initialized tracer and graders\n")

    # Step 3: Run eval trials with tracing
    console.print("[bold]Step 3:[/bold] Running eval trials...\n")
    trials = run_eval_trials(agent, tasks, tracer)
    logger.info("Completed %d trials, %d spans collected", len(trials), tracer.get_span_count())

    # Step 4: Grade with composite graders
    console.print("[bold]Step 4:[/bold] Grading responses...\n")
    eval_results = grade_trials(trials, tasks, grader)

    # Step 5: Run safety tests
    console.print("[bold]Step 5:[/bold] Running safety tests...\n")
    safety_tester = SafetyTester()
    safety_results = safety_tester.run_safety_suite(agent, adversarial_attacks)

    # Step 6: Run benchmarks (simulated)
    console.print("[bold]Step 6:[/bold] Running benchmarks...\n")
    benchmark_runner = BenchmarkRunner()
    # Use a subset of tasks for benchmark to keep output concise
    benchmark_tasks = tasks[:5]
    benchmark_entries = benchmark_runner.run_benchmark(benchmark_tasks)
    pareto_configs = benchmark_runner.find_pareto_optimal(benchmark_entries)

    # Step 7: Assemble and print report
    total_latency = sum(t.latency_ms for t in trials)
    total_cost = sum(e.cost_usd for e in benchmark_entries)
    passed_count = sum(1 for r in eval_results if r.pass_rate >= 0.5)
    blocked_count = sum(1 for r in safety_results if r.blocked)

    report = EvalReport(
        agent_name="Research Assistant",
        eval_results=eval_results,
        safety_results=safety_results,
        benchmark_entries=benchmark_entries,
        overall_pass_rate=passed_count / len(eval_results) if eval_results else 0.0,
        overall_safety_score=blocked_count / len(safety_results) if safety_results else 0.0,
        total_cost_usd=total_cost,
        total_latency_ms=total_latency,
    )

    console.print("[bold]Step 7:[/bold] Generating report...\n")
    reporter = EvalReporter(console)
    reporter.print_report(report)

    # Pareto analysis summary
    console.print(
        Panel(
            f"[bold]Pareto-optimal configs:[/bold] {', '.join(pareto_configs)}\n\n"
            "These configurations are not dominated on any axis\n"
            "(accuracy, latency, cost) by another configuration.",
            title="Pareto Analysis",
        )
    )

    # Trace summary
    console.print(
        f"\n[dim]Trace: {tracer.get_span_count()} spans, "
        f"{tracer.get_total_duration_ms():.0f}ms total duration[/dim]"
    )

    token_tracker.report()


if __name__ == "__main__":
    main()
