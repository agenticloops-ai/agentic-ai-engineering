"""
End-to-End Evaluation Pipeline

Demonstrates a complete eval pipeline: load golden dataset, run agent trials,
score with multiple graders, aggregate results, and detect regressions.
Reports pass@k (at least one success) and pass^k (all succeed) metrics,
and breaks down results by eval type (capability vs regression).
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shared.agent import ResearchAssistant
from shared.graders import GraderResult, KeywordGrader, SourceCitationGrader, ToolCallGrader
from shared.knowledge_base import KNOWLEDGE_BASE

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Pipeline data structures
# ---------------------------------------------------------------------------


@dataclass
class EvalTask:
    """A single evaluation task."""

    id: str
    question: str
    expected_keywords: list[str]
    expected_source_ids: list[str]
    difficulty: str
    category: str
    eval_type: str = "capability"  # "capability" (new feature) or "regression" (must not break)


@dataclass
class EvalTrial:
    """One run of an agent on a task."""

    task_id: str
    trial_number: int
    answer: str
    tool_calls: list[dict[str, Any]]
    sources: list[Any]
    latency_ms: float


@dataclass
class EvalResult:
    """Aggregated results for a task across trials."""

    task_id: str
    trials: list[EvalTrial]
    grader_results: dict[str, list[GraderResult]]
    pass_rate: float
    avg_score: float
    # pass@k: probability of at least one success in k trials (optimistic — measures capability)
    pass_at_k: float = 0.0
    # pass^k: probability that ALL k trials succeed (strict — measures consistency)
    pass_pow_k: float = 0.0


# ---------------------------------------------------------------------------
# Simulated responses for demo mode
# ---------------------------------------------------------------------------

# Each task maps to a list of trial responses; run_trial cycles through them.
# Variation across trials demonstrates the difference between pass@k and pass^k.
SIMULATED_RESPONSES: dict[str, dict[str, Any]] = {
    "task_001": {
        "answer": (
            "Based on doc_001, the key benefits of microservices "
            "architecture include scalability, fault isolation, and "
            "the ability to deploy services independently. Each "
            "service runs in its own process and communicates via "
            "APIs."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "microservices benefits"},
                "results": [KNOWLEDGE_BASE[0]],
            }
        ],
        "sources": [[KNOWLEDGE_BASE[0]]],
    },
    "task_002": {
        "answer": (
            "According to doc_002, REST API best practices include "
            "using nouns for endpoints (e.g., /users), HTTP methods "
            "for actions (GET, POST, PUT, DELETE), and proper status "
            "codes. Also use versioning and pagination for "
            "collections."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "REST API design"},
                "results": [KNOWLEDGE_BASE[1]],
            }
        ],
        "sources": [[KNOWLEDGE_BASE[1]]],
    },
    "task_003": {
        "answer": (
            "Per doc_003, database indexes improve query "
            "performance via efficient lookup structures. B-tree "
            "indexes handle equality and range queries. Use EXPLAIN "
            "to analyze query plans."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "database indexes"},
                "results": [KNOWLEDGE_BASE[2]],
            }
        ],
        "sources": [[KNOWLEDGE_BASE[2]]],
    },
    "task_004": {
        "answer": (
            "According to doc_004, authentication verifies identity "
            "(who you are), while authorization controls access "
            "(what you can do). JWT tokens provide stateless "
            "authentication. Always hash passwords with bcrypt or "
            "argon2."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "authentication authorization"},
                "results": [KNOWLEDGE_BASE[3]],
            }
        ],
        "sources": [[KNOWLEDGE_BASE[3]]],
    },
    "task_005": {
        "answer": (
            "Based on doc_005, key CI/CD practices include "
            "continuous integration that automatically builds and "
            "tests code on every commit, and continuous deployment "
            "that deploys passing builds to production. Fast "
            "feedback loops and trunk-based development are "
            "essential."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "CI/CD pipelines"},
                "results": [KNOWLEDGE_BASE[4]],
            }
        ],
        "sources": [[KNOWLEDGE_BASE[4]]],
    },
    "task_013": {
        "answer": (
            "I was unable to find any relevant information about "
            "programming languages for machine learning in the "
            "knowledge base. The available documents do not cover "
            "this topic."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "machine learning programming language"},
                "results": [],
            }
        ],
        "sources": [[]],
    },
}

# Trial-specific overrides to simulate non-deterministic LLM behavior.
# Missing trial numbers fall back to the default SIMULATED_RESPONSES entry.
SIMULATED_TRIAL_OVERRIDES: dict[str, dict[int, dict[str, Any]]] = {
    "task_001": {
        # Trial 2: weaker answer missing expected keywords — shows inconsistency
        2: {
            "answer": (
                "Microservices let you break an application into smaller "
                "services that communicate over the network."
            ),
            "tool_calls": [
                {
                    "name": "search_knowledge_base",
                    "input": {"query": "microservices benefits"},
                    "results": [KNOWLEDGE_BASE[0]],
                }
            ],
            "sources": [[KNOWLEDGE_BASE[0]]],
        },
    },
    "task_003": {
        # Trial 3: answer omits source citation — fails citation grader
        3: {
            "answer": (
                "Database indexes improve performance via efficient "
                "B-tree lookup structures. Use EXPLAIN to analyze "
                "query plans."
            ),
            "tool_calls": [
                {
                    "name": "search_knowledge_base",
                    "input": {"query": "database indexes"},
                    "results": [KNOWLEDGE_BASE[2]],
                }
            ],
            "sources": [[]],  # No sources cited
        },
    },
}


# ---------------------------------------------------------------------------
# Eval pipeline
# ---------------------------------------------------------------------------


class EvalPipeline:
    """End-to-end evaluation pipeline with multi-grader scoring."""

    def __init__(self, agent: ResearchAssistant | None = None) -> None:
        self.agent = agent
        self.keyword_grader = KeywordGrader()
        self.citation_grader = SourceCitationGrader()
        self.tool_grader = ToolCallGrader()

    def load_tasks(self, path: str) -> list[EvalTask]:
        """Load and parse evaluation tasks from a JSON file."""
        with Path(path).open(encoding="utf-8") as f:
            data = json.load(f)
        tasks = [
            EvalTask(
                id=t["id"],
                question=t["question"],
                expected_keywords=t["expected_keywords"],
                expected_source_ids=t["expected_source_ids"],
                difficulty=t["difficulty"],
                category=t["category"],
                eval_type=t.get("eval_type", "capability"),
            )
            for t in data["tasks"]
        ]
        logger.info("Loaded %d eval tasks from %s", len(tasks), path)
        return tasks

    def run_trial(self, task: EvalTask, trial_number: int = 1) -> EvalTrial:
        """Execute a single trial — run the agent and measure latency."""
        start = time.perf_counter()

        if self.agent is not None:
            try:
                response = self.agent.answer(task.question)
            except Exception as e:
                logger.error("Agent error on %s: %s", task.id, e)
                response = {"answer": f"Error: {e}", "tool_calls": [], "sources": []}
        else:
            # Check for trial-specific overrides first, then fall back to default
            overrides = SIMULATED_TRIAL_OVERRIDES.get(task.id, {})
            response = overrides.get(
                trial_number,
                SIMULATED_RESPONSES.get(
                    task.id,
                    {"answer": "No simulated response.", "tool_calls": [], "sources": []},
                ),
            )

        elapsed_ms = (time.perf_counter() - start) * 1000

        return EvalTrial(
            task_id=task.id,
            trial_number=0,
            answer=response["answer"],
            tool_calls=response.get("tool_calls", []),
            sources=response.get("sources", []),
            latency_ms=elapsed_ms,
        )

    def grade_trial(self, task: EvalTask, trial: EvalTrial) -> dict[str, GraderResult]:
        """Apply all graders to a single trial."""
        return {
            "keywords": self.keyword_grader.grade(trial.answer, task.expected_keywords),
            "citations": self.citation_grader.grade(trial.answer, task.expected_source_ids),
            "tool_calls": self.tool_grader.grade(trial.tool_calls),
        }

    def run_evaluation(self, tasks: list[EvalTask], num_trials: int = 1) -> list[EvalResult]:
        """Run the full evaluation: multiple trials per task, grade each."""
        results: list[EvalResult] = []

        for task in tasks:
            logger.info("Evaluating %s (%s, %s)", task.id, task.difficulty, task.category)
            trials: list[EvalTrial] = []
            all_grader_results: dict[str, list[GraderResult]] = {
                "keywords": [],
                "citations": [],
                "tool_calls": [],
            }

            for trial_num in range(num_trials):
                trial = self.run_trial(task, trial_number=trial_num + 1)
                trial.trial_number = trial_num + 1
                trials.append(trial)

                grader_results = self.grade_trial(task, trial)
                for name, result in grader_results.items():
                    all_grader_results[name].append(result)

            # Determine which trials passed (all graders must pass)
            pass_count = 0
            for i in range(num_trials):
                all_passed = all(all_grader_results[g][i].passed for g in all_grader_results)
                if all_passed:
                    pass_count += 1
            pass_rate = pass_count / num_trials

            # pass@k: at least one trial succeeded (optimistic — measures capability)
            pass_at_k = 1.0 if pass_count > 0 else 0.0
            # pass^k: ALL trials succeeded (strict — measures consistency/reliability)
            pass_pow_k = 1.0 if pass_count == num_trials else 0.0

            # Average score across all graders and trials
            all_scores = [
                r.score for grader_list in all_grader_results.values() for r in grader_list
            ]
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0

            results.append(
                EvalResult(
                    task_id=task.id,
                    trials=trials,
                    grader_results=all_grader_results,
                    pass_rate=pass_rate,
                    avg_score=avg_score,
                    pass_at_k=pass_at_k,
                    pass_pow_k=pass_pow_k,
                )
            )

        return results

    def detect_regressions(
        self, current: list[EvalResult], baseline: list[EvalResult]
    ) -> list[str]:
        """Compare current results against a baseline and flag regressions."""
        baseline_map = {r.task_id: r for r in baseline}
        regressions: list[str] = []

        for result in current:
            base = baseline_map.get(result.task_id)
            if base is None:
                continue

            # Flag if pass rate dropped
            if result.pass_rate < base.pass_rate:
                regressions.append(
                    f"{result.task_id}: pass rate {base.pass_rate:.0%} -> {result.pass_rate:.0%}"
                )

            # Flag if average score dropped significantly (> 0.1)
            if result.avg_score < base.avg_score - 0.1:
                regressions.append(
                    f"{result.task_id}: avg score {base.avg_score:.2f} -> {result.avg_score:.2f}"
                )

        return regressions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the end-to-end evaluation pipeline."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]Evaluation Pipeline[/bold cyan]\n\n"
            "End-to-end pipeline: load golden dataset, run agent trials,\n"
            "score with multiple graders, aggregate pass@k and pass^k,\n"
            "break down by eval type (capability vs regression), detect regressions.",
            title="Eval Tutorial 3",
        )
    )

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if has_api_key:
        console.print("[green]API key found — running live evaluation[/green]\n")
        client = anthropic.Anthropic()
        agent = ResearchAssistant(client, KNOWLEDGE_BASE)
    else:
        console.print("[yellow]No API key — using simulated responses for demo[/yellow]\n")
        agent = None

    pipeline = EvalPipeline(agent=agent)

    # Load tasks
    dataset_path = Path(__file__).parent / "datasets" / "golden_tasks.json"
    all_tasks = pipeline.load_tasks(str(dataset_path))

    # In simulated mode, limit to tasks with simulated responses
    if agent is None:
        eval_tasks = [t for t in all_tasks if t.id in SIMULATED_RESPONSES]
        console.print(f"Running {len(eval_tasks)} tasks (simulated mode)...\n")
    else:
        eval_tasks = all_tasks
        console.print(f"Running {len(eval_tasks)} tasks...\n")

    # Run evaluation — use 3 trials in simulated mode to demonstrate pass@k vs pass^k
    num_trials = 3 if agent is None else 1
    results = pipeline.run_evaluation(eval_tasks, num_trials=num_trials)

    # Per-task results table
    table = Table(title="Per-Task Results", show_lines=True)
    table.add_column("Task", style="cyan", width=12)
    table.add_column("Type", width=12)
    table.add_column("Difficulty", width=10)
    table.add_column("Keywords", width=10, justify="center")
    table.add_column("Citations", width=10, justify="center")
    table.add_column("Tools", width=10, justify="center")
    table.add_column("pass@k", width=8, justify="center")
    table.add_column("pass^k", width=8, justify="center")
    table.add_column("Latency", width=10, justify="right")

    def grader_cell(grader_name: str, eval_result: "EvalResult") -> str:
        """Format a grader score as a colored Rich cell."""
        scores = eval_result.grader_results[grader_name]
        avg = sum(r.score for r in scores) / len(scores) if scores else 0.0
        color = "green" if avg >= 0.7 else ("yellow" if avg >= 0.4 else "red")
        return f"[{color}]{avg:.0%}[/{color}]"

    for result in results:
        task = next(t for t in eval_tasks if t.id == result.task_id)

        avg_latency = sum(t.latency_ms for t in result.trials) / len(result.trials)
        at_k_color = "green" if result.pass_at_k == 1.0 else "red"
        pow_k_color = "green" if result.pass_pow_k == 1.0 else "red"

        table.add_row(
            result.task_id,
            task.eval_type,
            task.difficulty,
            grader_cell("keywords", result),
            grader_cell("citations", result),
            grader_cell("tool_calls", result),
            f"[{at_k_color}]{result.pass_at_k:.0%}[/{at_k_color}]",
            f"[{pow_k_color}]{result.pass_pow_k:.0%}[/{pow_k_color}]",
            f"{avg_latency:.0f}ms",
        )

    console.print(table)

    # Aggregate metrics
    total_at_k = sum(r.pass_at_k for r in results) / len(results) if results else 0.0
    total_pow_k = sum(r.pass_pow_k for r in results) / len(results) if results else 0.0
    total_score = sum(r.avg_score for r in results) / len(results) if results else 0.0

    # Per eval-type breakdown (capability vs regression)
    eval_types: dict[str, list[EvalResult]] = {}
    for result in results:
        task = next(t for t in eval_tasks if t.id == result.task_id)
        eval_types.setdefault(task.eval_type, []).append(result)

    type_table = Table(title="Per Eval-Type Breakdown")
    type_table.add_column("Eval Type", style="bold")
    type_table.add_column("Tasks", justify="center")
    type_table.add_column("pass@k", justify="center")
    type_table.add_column("pass^k", justify="center")
    type_table.add_column("Avg Score", justify="center")

    for etype, etype_results in sorted(eval_types.items()):
        e_at_k = sum(r.pass_at_k for r in etype_results) / len(etype_results)
        e_pow_k = sum(r.pass_pow_k for r in etype_results) / len(etype_results)
        e_score = sum(r.avg_score for r in etype_results) / len(etype_results)
        type_table.add_row(
            etype, str(len(etype_results)), f"{e_at_k:.0%}", f"{e_pow_k:.0%}", f"{e_score:.2f}"
        )

    console.print(type_table)

    # Per-category breakdown
    categories: dict[str, list[EvalResult]] = {}
    for result in results:
        task = next(t for t in eval_tasks if t.id == result.task_id)
        categories.setdefault(task.category, []).append(result)

    cat_table = Table(title="Per-Category Breakdown")
    cat_table.add_column("Category", style="bold")
    cat_table.add_column("Tasks", justify="center")
    cat_table.add_column("pass@k", justify="center")
    cat_table.add_column("pass^k", justify="center")
    cat_table.add_column("Avg Score", justify="center")

    for cat, cat_results in sorted(categories.items()):
        cat_at_k = sum(r.pass_at_k for r in cat_results) / len(cat_results)
        cat_pow_k = sum(r.pass_pow_k for r in cat_results) / len(cat_results)
        cat_score = sum(r.avg_score for r in cat_results) / len(cat_results)
        cat_table.add_row(
            cat, str(len(cat_results)), f"{cat_at_k:.0%}", f"{cat_pow_k:.0%}", f"{cat_score:.2f}"
        )

    console.print(cat_table)

    console.print(f"\n[bold]Overall pass@{num_trials}:[/bold] {total_at_k:.0%}")
    console.print(f"[bold]Overall pass^{num_trials}:[/bold] {total_pow_k:.0%}")
    console.print(f"[bold]Overall avg score:[/bold] {total_score:.2f}")

    # Regression detection demo
    # Simulate a "baseline" with slightly better scores for demonstration
    console.print("\n[bold]Regression Detection[/bold]")
    baseline = [
        EvalResult(
            task_id=r.task_id,
            trials=r.trials,
            grader_results=r.grader_results,
            pass_rate=min(r.pass_rate + 0.1, 1.0),
            avg_score=min(r.avg_score + 0.15, 1.0),
            pass_at_k=min(r.pass_at_k + 0.1, 1.0),
            pass_pow_k=min(r.pass_pow_k + 0.1, 1.0),
        )
        for r in results
    ]

    regressions = pipeline.detect_regressions(results, baseline)
    if regressions:
        console.print(f"[red]Found {len(regressions)} regression(s):[/red]")
        for reg in regressions:
            console.print(f"  [red]- {reg}[/red]")
    else:
        console.print("[green]No regressions detected[/green]")

    # Token usage
    if agent is not None:
        console.print()
        agent.token_tracker.report()


if __name__ == "__main__":
    main()
