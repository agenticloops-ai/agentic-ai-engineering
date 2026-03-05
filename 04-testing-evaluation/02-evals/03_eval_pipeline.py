"""
End-to-End Evaluation Pipeline

Demonstrates a complete eval pipeline: load golden dataset, run agent trials,
score with multiple graders, aggregate results, and detect regressions.
Reports pass@k metrics and per-grader breakdowns.
"""

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from common import AnthropicTokenTracker, setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Knowledge base and research assistant
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE = [
    {
        "id": "doc_001",
        "title": "Microservices Architecture",
        "content": (
            "Microservices architecture decomposes applications into "
            "small, independent services. Each service runs in its own "
            "process, communicates via APIs, and can be deployed "
            "independently. Benefits include scalability, fault "
            "isolation, and technology flexibility. Challenges include "
            "distributed system complexity, data consistency, and "
            "operational overhead."
        ),
        "tags": ["architecture", "microservices", "distributed-systems"],
    },
    {
        "id": "doc_002",
        "title": "REST API Design",
        "content": (
            "REST APIs follow resource-oriented design principles. "
            "Use nouns for endpoints (e.g., /users, /orders), HTTP "
            "methods for actions (GET, POST, PUT, DELETE), and status "
            "codes for results. Best practices include versioning "
            "(e.g., /v1/), pagination for collections, and consistent "
            "error response formats."
        ),
        "tags": ["api", "rest", "design"],
    },
    {
        "id": "doc_003",
        "title": "Database Indexing",
        "content": (
            "Database indexes improve query performance by creating "
            "efficient lookup structures. B-tree indexes handle "
            "equality and range queries. Composite indexes support "
            "multi-column queries but column order matters. "
            "Over-indexing slows writes and wastes storage. Use "
            "EXPLAIN to analyze query plans and identify missing "
            "indexes."
        ),
        "tags": ["database", "performance", "indexing"],
    },
    {
        "id": "doc_004",
        "title": "Authentication and Authorization",
        "content": (
            "Authentication verifies identity (who you are), "
            "authorization controls access (what you can do). JWT "
            "tokens enable stateless authentication with claims-based "
            "authorization. OAuth 2.0 provides delegated access. "
            "Always hash passwords with bcrypt or argon2. Implement "
            "rate limiting and account lockout to prevent brute force "
            "attacks."
        ),
        "tags": ["security", "authentication", "authorization"],
    },
    {
        "id": "doc_005",
        "title": "CI/CD Pipelines",
        "content": (
            "Continuous Integration (CI) automatically builds and "
            "tests code on every commit. Continuous Deployment (CD) "
            "automatically deploys passing builds to production. Key "
            "practices: fast feedback loops, trunk-based development, "
            "feature flags for gradual rollouts, and automated "
            "rollback on failure. Tools include GitHub Actions, "
            "GitLab CI, and Jenkins."
        ),
        "tags": ["devops", "ci-cd", "automation"],
    },
    {
        "id": "doc_006",
        "title": "Container Orchestration with Kubernetes",
        "content": (
            "Kubernetes manages containerized workloads across "
            "clusters. Core concepts: Pods (smallest deployable "
            "units), Services (network abstraction), Deployments "
            "(declarative updates), and ConfigMaps/Secrets "
            "(configuration). Key features include auto-scaling, "
            "self-healing, rolling updates, and service discovery."
        ),
        "tags": ["devops", "kubernetes", "containers"],
    },
    {
        "id": "doc_007",
        "title": "Event-Driven Architecture",
        "content": (
            "Event-driven architecture uses events to trigger and "
            "communicate between services. Patterns include event "
            "sourcing (storing state as events), CQRS (separating "
            "reads and writes), and pub/sub messaging. Benefits: "
            "loose coupling, scalability, audit trails. Challenges: "
            "eventual consistency, event ordering, and debugging "
            "distributed flows."
        ),
        "tags": ["architecture", "events", "messaging"],
    },
    {
        "id": "doc_008",
        "title": "Caching Strategies",
        "content": (
            "Caching reduces latency and database load by storing "
            "frequently accessed data in memory. Strategies include "
            "cache-aside (application manages cache), write-through "
            "(cache updated on writes), and write-behind (async cache "
            "writes). Use Redis or Memcached for distributed caching. "
            "Set appropriate TTLs and implement cache invalidation "
            "carefully."
        ),
        "tags": ["performance", "caching", "redis"],
    },
]

SYSTEM_PROMPT = (
    "You are a research assistant. Answer questions using ONLY the information from the "
    "search results provided via tools. Always cite your sources by document ID. "
    "If no relevant information is found, say so clearly. Do not make up information."
)

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the knowledge base for documents matching a "
            "query. Returns relevant documents with their content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant documents",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of documents to return (default: 3)",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
]


class ResearchAssistant:
    """Research assistant that searches a knowledge base and synthesizes answers."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        knowledge_base: list[dict[str, Any]],
        model: str = "claude-sonnet-4-5-20250929",
    ) -> None:
        self.client = client
        self.knowledge_base = knowledge_base
        self.model = model
        self.token_tracker = AnthropicTokenTracker()

    def search_knowledge_base(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        """Search knowledge base using keyword matching."""
        query_words = set(query.lower().split())
        scored: list[tuple[int, dict[str, Any]]] = []
        for doc in self.knowledge_base:
            text = f"{doc['title']} {doc['content']} {' '.join(doc['tags'])}".lower()
            score = sum(1 for word in query_words if word in text)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:max_results]]

    def answer(self, question: str) -> dict[str, Any]:
        """Answer a question using the knowledge base."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        tool_calls_made: list[dict[str, Any]] = []

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            if response.stop_reason != "tool_use":
                answer_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        answer_text += block.text
                return {
                    "answer": answer_text,
                    "tool_calls": tool_calls_made,
                    "sources": [tc["results"] for tc in tool_calls_made],
                }

            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self.search_knowledge_base(**block.input)
                    tool_calls_made.append(
                        {"name": block.name, "input": block.input, "results": result}
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Graders (reused from 01_code_based_graders)
# ---------------------------------------------------------------------------


@dataclass
class GraderResult:
    """Result from a grader evaluation."""

    passed: bool
    score: float
    reason: str


class KeywordGrader:
    """Grades based on required keywords in the answer."""

    def grade(self, answer: str, expected_keywords: list[str]) -> GraderResult:
        """Check whether the answer contains the expected keywords."""
        answer_lower = answer.lower()
        found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
        score = len(found) / len(expected_keywords) if expected_keywords else 1.0
        passed = score >= 0.5
        missing = [kw for kw in expected_keywords if kw.lower() not in answer_lower]
        reason = f"Found {len(found)}/{len(expected_keywords)} keywords"
        if missing:
            reason += f" (missing: {', '.join(missing)})"
        return GraderResult(passed=passed, score=score, reason=reason)


class SourceCitationGrader:
    """Grades whether the answer cites its sources."""

    def grade(self, answer: str, expected_source_ids: list[str]) -> GraderResult:
        """Check whether expected document IDs are cited in the answer."""
        if not expected_source_ids:
            has_refusal = bool(
                re.search(
                    r"no relevant|not found|no information|cannot find", answer, re.IGNORECASE
                )
            )
            return GraderResult(
                passed=has_refusal,
                score=1.0 if has_refusal else 0.0,
                reason="Out-of-scope: " + ("correctly refused" if has_refusal else "should refuse"),
            )

        cited = [sid for sid in expected_source_ids if sid in answer]
        score = len(cited) / len(expected_source_ids)
        passed = score >= 0.5
        missing = [sid for sid in expected_source_ids if sid not in answer]
        reason = f"Cited {len(cited)}/{len(expected_source_ids)} sources"
        if missing:
            reason += f" (missing: {', '.join(missing)})"
        return GraderResult(passed=passed, score=score, reason=reason)


class ToolCallGrader:
    """Grades whether the agent made expected tool calls."""

    def grade(
        self, tool_calls: list[dict[str, Any]], expected_tool: str = "search_knowledge_base"
    ) -> GraderResult:
        """Verify the agent called the expected tool at least once."""
        tool_names = [tc.get("name", "") for tc in tool_calls]
        called = expected_tool in tool_names
        score = 1.0 if called else 0.0
        reason = (
            f"Tool '{expected_tool}' was called ({len(tool_calls)} total calls)"
            if called
            else f"Tool '{expected_tool}' was NOT called"
        )
        return GraderResult(passed=called, score=score, reason=reason)


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


# ---------------------------------------------------------------------------
# Simulated responses for demo mode
# ---------------------------------------------------------------------------

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
            )
            for t in data["tasks"]
        ]
        logger.info("Loaded %d eval tasks from %s", len(tasks), path)
        return tasks

    def run_trial(self, task: EvalTask) -> EvalTrial:
        """Execute a single trial — run the agent and measure latency."""
        start = time.perf_counter()

        if self.agent is not None:
            try:
                response = self.agent.answer(task.question)
            except Exception as e:
                logger.error("Agent error on %s: %s", task.id, e)
                response = {"answer": f"Error: {e}", "tool_calls": [], "sources": []}
        else:
            response = SIMULATED_RESPONSES.get(
                task.id,
                {"answer": "No simulated response.", "tool_calls": [], "sources": []},
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
                trial = self.run_trial(task)
                trial.trial_number = trial_num + 1
                trials.append(trial)

                grader_results = self.grade_trial(task, trial)
                for name, result in grader_results.items():
                    all_grader_results[name].append(result)

            # Aggregate: pass@k = fraction of trials where ALL graders passed
            pass_count = 0
            for i in range(num_trials):
                all_passed = all(all_grader_results[g][i].passed for g in all_grader_results)
                if all_passed:
                    pass_count += 1
            pass_rate = pass_count / num_trials

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
            "score with multiple graders, aggregate pass@k, detect regressions.",
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

    # Run evaluation
    num_trials = 1
    results = pipeline.run_evaluation(eval_tasks, num_trials=num_trials)

    # Per-task results table
    table = Table(title="Per-Task Results", show_lines=True)
    table.add_column("Task", style="cyan", width=12)
    table.add_column("Category", width=14)
    table.add_column("Difficulty", width=10)
    table.add_column("Keywords", width=12, justify="center")
    table.add_column("Citations", width=12, justify="center")
    table.add_column("Tool Calls", width=12, justify="center")
    table.add_column("Pass Rate", width=10, justify="center")
    table.add_column("Latency", width=10, justify="right")

    def grader_cell(grader_name: str, eval_result: "EvalResult") -> str:
        """Format a grader score as a colored Rich cell."""
        scores = eval_result.grader_results[grader_name]
        avg = sum(r.score for r in scores) / len(scores) if scores else 0.0
        color = "green" if avg >= 0.7 else ("yellow" if avg >= 0.4 else "red")
        return f"[{color}]{avg:.0%}[/{color}]"

    for result in results:
        task = next(t for t in eval_tasks if t.id == result.task_id)

        pass_color = (
            "green" if result.pass_rate >= 0.8 else ("yellow" if result.pass_rate >= 0.5 else "red")
        )
        avg_latency = sum(t.latency_ms for t in result.trials) / len(result.trials)

        table.add_row(
            result.task_id,
            task.category,
            task.difficulty,
            grader_cell("keywords", result),
            grader_cell("citations", result),
            grader_cell("tool_calls", result),
            f"[{pass_color}]{result.pass_rate:.0%}[/{pass_color}]",
            f"{avg_latency:.0f}ms",
        )

    console.print(table)

    # Aggregate metrics
    total_pass = sum(r.pass_rate for r in results) / len(results) if results else 0.0
    total_score = sum(r.avg_score for r in results) / len(results) if results else 0.0

    # Per-category breakdown
    categories: dict[str, list[EvalResult]] = {}
    for result in results:
        task = next(t for t in eval_tasks if t.id == result.task_id)
        categories.setdefault(task.category, []).append(result)

    cat_table = Table(title="Per-Category Breakdown")
    cat_table.add_column("Category", style="bold")
    cat_table.add_column("Tasks", justify="center")
    cat_table.add_column("Avg Pass Rate", justify="center")
    cat_table.add_column("Avg Score", justify="center")

    for cat, cat_results in sorted(categories.items()):
        cat_pass = sum(r.pass_rate for r in cat_results) / len(cat_results)
        cat_score = sum(r.avg_score for r in cat_results) / len(cat_results)
        cat_table.add_row(cat, str(len(cat_results)), f"{cat_pass:.0%}", f"{cat_score:.2f}")

    console.print(cat_table)

    console.print(f"\n[bold]Overall pass@{num_trials}:[/bold] {total_pass:.0%}")
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
