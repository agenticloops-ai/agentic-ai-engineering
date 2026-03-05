"""
Model Comparison Benchmark

Benchmarks the same research assistant tasks across multiple models and providers.
Measures accuracy (keyword matching), latency, token usage, and cost per query.
Supports both live API calls and a simulated mode for demo without API keys.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import anthropic
import openai
from common import AnthropicTokenTracker, OpenAITokenTracker, setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Knowledge base (shared research assistant corpus)
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE = [
    {
        "id": "doc_001",
        "title": "Microservices Architecture",
        "content": (
            "Microservices architecture decomposes applications into small, "
            "independent services. Each service runs in its own process, "
            "communicates via APIs, and can be deployed independently. "
            "Benefits include scalability, fault isolation, and technology "
            "flexibility. Challenges include distributed system complexity, "
            "data consistency, and operational overhead."
        ),
        "tags": ["architecture", "microservices", "distributed-systems"],
    },
    {
        "id": "doc_002",
        "title": "REST API Design",
        "content": (
            "REST APIs follow resource-oriented design principles. "
            "Use nouns for endpoints, HTTP methods for actions, and "
            "status codes for results. Best practices include versioning, "
            "pagination for collections, and consistent error response "
            "formats."
        ),
        "tags": ["api", "rest", "design"],
    },
    {
        "id": "doc_003",
        "title": "Database Indexing",
        "content": (
            "Database indexes improve query performance by creating "
            "efficient lookup structures. B-tree indexes handle equality "
            "and range queries. Composite indexes support multi-column "
            "queries but column order matters. Over-indexing slows writes "
            "and wastes storage."
        ),
        "tags": ["database", "performance", "indexing"],
    },
    {
        "id": "doc_004",
        "title": "Authentication and Authorization",
        "content": (
            "Authentication verifies identity, authorization controls "
            "access. JWT tokens enable stateless authentication. "
            "OAuth 2.0 provides delegated access. Always hash passwords "
            "with bcrypt or argon2."
        ),
        "tags": ["security", "authentication", "authorization"],
    },
    {
        "id": "doc_005",
        "title": "CI/CD Pipelines",
        "content": (
            "CI automatically builds and tests code on every commit. "
            "CD automatically deploys passing builds. Key practices: "
            "fast feedback loops, trunk-based development, feature "
            "flags, and automated rollback."
        ),
        "tags": ["devops", "ci-cd", "automation"],
    },
    {
        "id": "doc_006",
        "title": "Container Orchestration with Kubernetes",
        "content": (
            "Kubernetes manages containerized workloads. Core concepts: "
            "Pods, Services, Deployments, ConfigMaps/Secrets. Key "
            "features: auto-scaling, self-healing, rolling updates, "
            "service discovery."
        ),
        "tags": ["devops", "kubernetes", "containers"],
    },
    {
        "id": "doc_007",
        "title": "Event-Driven Architecture",
        "content": (
            "Event-driven architecture uses events to trigger "
            "communication between services. Patterns: event sourcing, "
            "CQRS, pub/sub. Benefits: loose coupling, scalability, "
            "audit trails."
        ),
        "tags": ["architecture", "events", "messaging"],
    },
    {
        "id": "doc_008",
        "title": "Caching Strategies",
        "content": (
            "Caching reduces latency by storing frequently accessed "
            "data in memory. Strategies: cache-aside, write-through, "
            "write-behind. Use Redis or Memcached for distributed "
            "caching."
        ),
        "tags": ["performance", "caching", "redis"],
    },
]

SYSTEM_PROMPT = (
    "You are a research assistant. Answer questions using ONLY the information from the "
    "search results provided via tools. Always cite your sources by document ID. "
    "If no relevant information is found, say so clearly. Do not make up information."
)

# Anthropic tool format
TOOLS_ANTHROPIC = [
    {
        "name": "search_knowledge_base",
        "description": "Search the knowledge base for documents matching a query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max documents to return",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
]

# OpenAI tool format
TOOLS_OPENAI = [
    {
        "type": "function",
        "name": "search_knowledge_base",
        "description": "Search the knowledge base for documents matching a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max documents to return",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
]

# ---------------------------------------------------------------------------
# Benchmark tasks (subset of golden dataset)
# ---------------------------------------------------------------------------

BENCHMARK_TASKS = [
    {
        "id": "bench_001",
        "question": "What are the key benefits of microservices architecture?",
        "expected_keywords": ["scalability", "fault isolation", "independent"],
        "category": "architecture",
    },
    {
        "id": "bench_002",
        "question": "How should REST API endpoints be designed?",
        "expected_keywords": ["nouns", "http methods", "status codes"],
        "category": "api",
    },
    {
        "id": "bench_003",
        "question": "What strategies exist for database indexing?",
        "expected_keywords": ["b-tree", "composite", "query performance"],
        "category": "database",
    },
    {
        "id": "bench_004",
        "question": "Explain the difference between authentication and authorization.",
        "expected_keywords": ["identity", "access", "jwt", "oauth"],
        "category": "security",
    },
    {
        "id": "bench_005",
        "question": "What are the key practices in CI/CD?",
        "expected_keywords": ["continuous", "automated", "feedback"],
        "category": "devops",
    },
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """Configuration for a model to benchmark."""

    name: str
    provider: str  # "anthropic" or "openai"
    model_id: str
    cost_per_input_token: float  # dollars per 1M tokens
    cost_per_output_token: float  # dollars per 1M tokens


@dataclass
class BenchmarkResult:
    """Result from running one task on one model."""

    task_id: str
    model_name: str
    answer: str
    keyword_score: float  # 0.0-1.0 based on expected keywords found
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_calls: int


# Default model configurations
MODEL_CONFIGS = [
    ModelConfig("Claude Sonnet", "anthropic", "claude-sonnet-4-5-20250929", 3.0, 15.0),
    ModelConfig("Claude Haiku", "anthropic", "claude-haiku-4-5-20251001", 0.80, 4.0),
    ModelConfig("GPT-4.1 mini", "openai", "gpt-4.1-mini", 0.40, 1.60),
]

# ---------------------------------------------------------------------------
# Simulated results for demo mode
# ---------------------------------------------------------------------------

SIMULATED_RESULTS = [
    # bench_001 — Microservices
    BenchmarkResult(
        "bench_001",
        "Claude Sonnet",
        "Microservices offer scalability, fault isolation, and independent deployment (doc_001).",
        0.9,
        1200,
        150,
        200,
        0.0035,
        1,
    ),
    BenchmarkResult(
        "bench_001",
        "Claude Haiku",
        "Benefits include fault isolation and scalability (doc_001).",
        0.7,
        450,
        130,
        150,
        0.0007,
        1,
    ),
    BenchmarkResult(
        "bench_001",
        "GPT-4.1 mini",
        "Key benefits are scalability, fault isolation, and independent services (doc_001).",
        0.8,
        800,
        140,
        180,
        0.0003,
        1,
    ),
    # bench_002 — REST API
    BenchmarkResult(
        "bench_002",
        "Claude Sonnet",
        (
            "REST APIs use nouns for endpoints, HTTP methods for "
            "actions, and status codes for results (doc_002)."
        ),
        1.0,
        1150,
        145,
        190,
        0.0033,
        1,
    ),
    BenchmarkResult(
        "bench_002",
        "Claude Haiku",
        "Use nouns and HTTP methods with proper status codes (doc_002).",
        0.8,
        420,
        125,
        140,
        0.0007,
        1,
    ),
    BenchmarkResult(
        "bench_002",
        "GPT-4.1 mini",
        "Design endpoints with nouns, use HTTP methods and status codes (doc_002).",
        0.9,
        780,
        135,
        170,
        0.0003,
        1,
    ),
    # bench_003 — Database Indexing
    BenchmarkResult(
        "bench_003",
        "Claude Sonnet",
        (
            "B-tree indexes handle equality queries, composite indexes "
            "support multi-column query performance (doc_003)."
        ),
        0.9,
        1300,
        155,
        210,
        0.0036,
        1,
    ),
    BenchmarkResult(
        "bench_003",
        "Claude Haiku",
        "Database indexes improve query performance using B-tree structures (doc_003).",
        0.6,
        440,
        128,
        145,
        0.0007,
        1,
    ),
    BenchmarkResult(
        "bench_003",
        "GPT-4.1 mini",
        "B-tree and composite indexes improve query performance (doc_003).",
        0.8,
        820,
        138,
        175,
        0.0003,
        1,
    ),
    # bench_004 — Auth
    BenchmarkResult(
        "bench_004",
        "Claude Sonnet",
        (
            "Authentication verifies identity while authorization "
            "controls access. JWT and OAuth 2.0 are key mechanisms "
            "(doc_004)."
        ),
        0.9,
        1250,
        148,
        205,
        0.0035,
        1,
    ),
    BenchmarkResult(
        "bench_004",
        "Claude Haiku",
        "Authentication is identity, authorization is access. Use JWT tokens (doc_004).",
        0.6,
        430,
        122,
        138,
        0.0006,
        1,
    ),
    BenchmarkResult(
        "bench_004",
        "GPT-4.1 mini",
        (
            "Authentication verifies identity, authorization controls "
            "access via JWT and OAuth (doc_004)."
        ),
        0.8,
        810,
        132,
        172,
        0.0003,
        1,
    ),
    # bench_005 — CI/CD
    BenchmarkResult(
        "bench_005",
        "Claude Sonnet",
        (
            "CI provides continuous integration with automated testing "
            "and fast feedback loops (doc_005)."
        ),
        0.8,
        1180,
        142,
        195,
        0.0034,
        1,
    ),
    BenchmarkResult(
        "bench_005",
        "Claude Haiku",
        "Continuous integration with automated builds and fast feedback (doc_005).",
        0.7,
        460,
        126,
        142,
        0.0007,
        1,
    ),
    BenchmarkResult(
        "bench_005",
        "GPT-4.1 mini",
        "Key CI/CD practices include continuous automated testing and feedback loops (doc_005).",
        0.7,
        790,
        130,
        168,
        0.0003,
        1,
    ),
]

# ---------------------------------------------------------------------------
# Knowledge base search utility
# ---------------------------------------------------------------------------


def search_knowledge_base(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    """Search knowledge base using keyword matching."""
    query_words = set(query.lower().split())
    scored: list[tuple[int, dict[str, Any]]] = []
    for doc in KNOWLEDGE_BASE:
        text = f"{doc['title']} {doc['content']} {' '.join(doc['tags'])}".lower()
        score = sum(1 for word in query_words if word in text)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:max_results]]


# ---------------------------------------------------------------------------
# Model benchmark class
# ---------------------------------------------------------------------------


class ModelBenchmark:
    """Benchmarks the same tasks across multiple models."""

    def __init__(self) -> None:
        self.anthropic_tracker = AnthropicTokenTracker()
        self.openai_tracker = OpenAITokenTracker()

    def score_answer(self, answer: str, expected_keywords: list[str]) -> float:
        """Score an answer based on expected keyword coverage."""
        answer_lower = answer.lower()
        found = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
        return found / len(expected_keywords) if expected_keywords else 1.0

    def run_task_anthropic(self, task: dict, config: ModelConfig) -> BenchmarkResult:
        """Run a single benchmark task using the Anthropic API."""
        client = anthropic.Anthropic()
        messages: list[dict[str, Any]] = [{"role": "user", "content": task["question"]}]
        tool_call_count = 0

        start = time.perf_counter()

        # Agent loop — handle tool use until final response
        while True:
            response = client.messages.create(
                model=config.model_id,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS_ANTHROPIC,
                messages=messages,
            )
            self.anthropic_tracker.track(response.usage)

            if response.stop_reason != "tool_use":
                answer = "".join(b.text for b in response.content if hasattr(b, "text"))
                break

            # Process tool calls
            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_call_count += 1
                    result = search_knowledge_base(**block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

        latency_ms = (time.perf_counter() - start) * 1000
        input_tok = response.usage.input_tokens
        output_tok = response.usage.output_tokens
        cost = (
            input_tok * config.cost_per_input_token + output_tok * config.cost_per_output_token
        ) / 1_000_000

        return BenchmarkResult(
            task_id=task["id"],
            model_name=config.name,
            answer=answer,
            keyword_score=self.score_answer(answer, task["expected_keywords"]),
            latency_ms=latency_ms,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
            tool_calls=tool_call_count,
        )

    def run_task_openai(self, task: dict, config: ModelConfig) -> BenchmarkResult:
        """Run a single benchmark task using the OpenAI API."""
        client = openai.OpenAI()
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": task["question"]},
        ]
        tool_call_count = 0

        start = time.perf_counter()

        # Agent loop — handle function calls until final response
        while True:
            response = client.responses.create(
                model=config.model_id,
                instructions=SYSTEM_PROMPT,
                max_output_tokens=1024,
                tools=TOOLS_OPENAI,
                input=messages,
            )
            self.openai_tracker.track(response.usage)

            function_calls = [o for o in response.output if o.type == "function_call"]

            if not function_calls:
                answer = response.output_text or ""
                break

            # Process function calls
            messages.extend(response.output)
            for func_call in function_calls:
                tool_call_count += 1
                args = json.loads(func_call.arguments)
                result = search_knowledge_base(**args)
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": func_call.call_id,
                        "output": json.dumps(result),
                    }
                )

        latency_ms = (time.perf_counter() - start) * 1000
        input_tok = response.usage.input_tokens
        output_tok = response.usage.output_tokens
        cost = (
            input_tok * config.cost_per_input_token + output_tok * config.cost_per_output_token
        ) / 1_000_000

        return BenchmarkResult(
            task_id=task["id"],
            model_name=config.name,
            answer=answer,
            keyword_score=self.score_answer(answer, task["expected_keywords"]),
            latency_ms=latency_ms,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
            tool_calls=tool_call_count,
        )

    def run_benchmark(self, tasks: list[dict], configs: list[ModelConfig]) -> list[BenchmarkResult]:
        """Run all tasks across all model configurations."""
        results: list[BenchmarkResult] = []
        for config in configs:
            logger.info("Benchmarking model: %s (%s)", config.name, config.model_id)
            for task in tasks:
                logger.info("  Task %s: %s", task["id"], task["question"][:50])
                try:
                    if config.provider == "anthropic":
                        result = self.run_task_anthropic(task, config)
                    elif config.provider == "openai":
                        result = self.run_task_openai(task, config)
                    else:
                        logger.error("Unknown provider: %s", config.provider)
                        continue
                    results.append(result)
                    logger.info(
                        "    score=%.2f, latency=%dms, cost=$%.4f",
                        result.keyword_score,
                        result.latency_ms,
                        result.cost_usd,
                    )
                except Exception as e:
                    logger.error("    Error: %s", e)
        return results


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def aggregate_by_model(results: list[BenchmarkResult]) -> dict[str, dict[str, float]]:
    """Compute per-model averages across all tasks."""
    model_results: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        model_results.setdefault(r.model_name, []).append(r)

    summaries: dict[str, dict[str, float]] = {}
    for model, mrs in model_results.items():
        n = len(mrs)
        summaries[model] = {
            "accuracy": sum(r.keyword_score for r in mrs) / n,
            "avg_latency_ms": sum(r.latency_ms for r in mrs) / n,
            "avg_tokens": sum(r.input_tokens + r.output_tokens for r in mrs) / n,
            "avg_cost": sum(r.cost_usd for r in mrs) / n,
            "tasks": n,
        }
    return summaries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run model comparison benchmark and display results."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]Model Comparison Benchmark[/bold cyan]\n\n"
            "Compares the same research assistant tasks across multiple models.\n"
            "Measures: accuracy (keyword match), latency, token usage, and cost.",
            title="Benchmark Tutorial 1",
        )
    )

    # Determine mode: live or simulated
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    live_mode = has_anthropic and has_openai

    if live_mode:
        console.print("[green]API keys found — running live benchmark[/green]\n")
        benchmark = ModelBenchmark()
        results = benchmark.run_benchmark(BENCHMARK_TASKS, MODEL_CONFIGS)
    else:
        console.print("[yellow]API keys missing — using simulated results for demo[/yellow]\n")
        results = SIMULATED_RESULTS

    # Per-task detail table
    detail_table = Table(title="Per-Task Results", show_lines=True)
    detail_table.add_column("Task", style="cyan", width=10)
    detail_table.add_column("Model", width=14)
    detail_table.add_column("Score", justify="center", width=7)
    detail_table.add_column("Latency", justify="right", width=9)
    detail_table.add_column("Tokens", justify="right", width=8)
    detail_table.add_column("Cost", justify="right", width=9)
    detail_table.add_column("Tools", justify="center", width=6)

    for r in results:
        score_color = (
            "green" if r.keyword_score >= 0.8 else ("yellow" if r.keyword_score >= 0.5 else "red")
        )
        detail_table.add_row(
            r.task_id,
            r.model_name,
            f"[{score_color}]{r.keyword_score:.0%}[/{score_color}]",
            f"{r.latency_ms:.0f}ms",
            str(r.input_tokens + r.output_tokens),
            f"${r.cost_usd:.4f}",
            str(r.tool_calls),
        )

    console.print(detail_table)
    console.print()

    # Aggregated comparison table
    summaries = aggregate_by_model(results)

    summary_table = Table(title="Model Comparison Summary", show_lines=True)
    summary_table.add_column("Model", style="bold", width=14)
    summary_table.add_column("Accuracy", justify="center", width=10)
    summary_table.add_column("Avg Latency", justify="right", width=12)
    summary_table.add_column("Avg Tokens", justify="right", width=12)
    summary_table.add_column("Avg Cost", justify="right", width=10)

    for model, stats in summaries.items():
        acc = stats["accuracy"]
        acc_color = "green" if acc >= 0.8 else ("yellow" if acc >= 0.6 else "red")
        summary_table.add_row(
            model,
            f"[{acc_color}]{acc:.0%}[/{acc_color}]",
            f"{stats['avg_latency_ms']:.0f}ms",
            f"{stats['avg_tokens']:.0f}",
            f"${stats['avg_cost']:.4f}",
        )

    console.print(summary_table)

    # Highlight best model per dimension
    console.print("\n[bold]Best Model by Dimension[/bold]")
    best_acc = max(summaries.items(), key=lambda x: x[1]["accuracy"])
    best_lat = min(summaries.items(), key=lambda x: x[1]["avg_latency_ms"])
    best_cost = min(summaries.items(), key=lambda x: x[1]["avg_cost"])
    console.print(f"  Accuracy:  {best_acc[0]} ({best_acc[1]['accuracy']:.0%})")
    console.print(f"  Latency:   {best_lat[0]} ({best_lat[1]['avg_latency_ms']:.0f}ms)")
    console.print(f"  Cost:      {best_cost[0]} (${best_cost[1]['avg_cost']:.4f})")

    # Token usage report (live mode)
    if live_mode:
        console.print()
        benchmark.anthropic_tracker.report()
        benchmark.openai_tracker.report()


if __name__ == "__main__":
    main()
