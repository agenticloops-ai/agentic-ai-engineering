"""
Full Benchmark Suite

Combines model and prompt comparisons into a configuration matrix.
Runs all model x prompt combinations, computes aggregate statistics,
performs Pareto analysis (identifying non-dominated configurations),
and generates a summary report. Works standalone with simulated results.
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
# Benchmark tasks
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
# Prompt strategies
# ---------------------------------------------------------------------------

PROMPT_STRATEGIES = {
    "zero_shot": (
        "You are a research assistant. Answer questions using ONLY the information from the "
        "search results provided via tools. Cite your sources."
    ),
    "few_shot": (
        "You are a research assistant. Answer questions using ONLY the information from the "
        "search results provided via tools. Cite your sources.\n\n"
        "Example:\n"
        "Question: What is REST?\n"
        "Answer: REST (Representational State Transfer) is an architectural style for APIs "
        "(doc_002). It uses resource-oriented design with HTTP methods for actions.\n\n"
        "Now answer the user's question in the same format."
    ),
    "chain_of_thought": (
        "You are a research assistant. Answer questions using ONLY the information from the "
        "search results provided via tools. Cite your sources.\n\n"
        "Think step by step:\n"
        "1. Search for relevant documents\n"
        "2. Extract key facts from each document\n"
        "3. Synthesize a comprehensive answer\n"
        "4. Cite all sources used"
    ),
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """Configuration for a model to benchmark."""

    name: str
    provider: str
    model_id: str
    cost_per_input_token: float
    cost_per_output_token: float


@dataclass
class BenchmarkConfig:
    """A single benchmark configuration (model + prompt combination)."""

    name: str
    model: ModelConfig
    prompt_strategy: str
    system_prompt: str


@dataclass
class BenchmarkResult:
    """Result from running one task with one configuration."""

    task_id: str
    config_name: str
    answer: str
    keyword_score: float
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_calls: int


MODEL_CONFIGS = [
    ModelConfig("Claude Sonnet", "anthropic", "claude-sonnet-4-5-20250929", 3.0, 15.0),
    ModelConfig("Claude Haiku", "anthropic", "claude-haiku-4-5-20251001", 0.80, 4.0),
    ModelConfig("GPT-4.1 mini", "openai", "gpt-4.1-mini", 0.40, 1.60),
]

# ---------------------------------------------------------------------------
# Simulated results for demo mode (3 models x 3 prompts x 5 tasks = 45 results)
# ---------------------------------------------------------------------------


def _build_simulated_results() -> dict[str, list[BenchmarkResult]]:
    """Build simulated results for the full configuration matrix."""
    # (config_name, task_id) -> (score, latency, in_tok, out_tok, cost)
    sim_data: dict[str, list[tuple[str, float, float, int, int, float]]] = {
        "Claude Sonnet + zero_shot": [
            ("bench_001", 0.8, 1100, 150, 180, 0.0031),
            ("bench_002", 0.8, 1080, 145, 175, 0.0031),
            ("bench_003", 0.7, 1150, 155, 185, 0.0032),
            ("bench_004", 0.6, 1090, 148, 178, 0.0031),
            ("bench_005", 0.7, 1120, 146, 176, 0.0031),
        ],
        "Claude Sonnet + few_shot": [
            ("bench_001", 0.9, 1250, 190, 200, 0.0036),
            ("bench_002", 1.0, 1230, 185, 195, 0.0035),
            ("bench_003", 0.9, 1300, 195, 210, 0.0037),
            ("bench_004", 0.8, 1240, 188, 198, 0.0036),
            ("bench_005", 0.9, 1260, 186, 196, 0.0035),
        ],
        "Claude Sonnet + chain_of_thought": [
            ("bench_001", 0.9, 1500, 200, 260, 0.0045),
            ("bench_002", 1.0, 1480, 195, 255, 0.0044),
            ("bench_003", 0.9, 1550, 205, 270, 0.0047),
            ("bench_004", 1.0, 1490, 198, 258, 0.0045),
            ("bench_005", 0.9, 1520, 196, 256, 0.0045),
        ],
        "Claude Haiku + zero_shot": [
            ("bench_001", 0.6, 420, 125, 130, 0.0006),
            ("bench_002", 0.6, 410, 120, 125, 0.0006),
            ("bench_003", 0.5, 440, 128, 135, 0.0006),
            ("bench_004", 0.4, 415, 122, 128, 0.0006),
            ("bench_005", 0.5, 430, 124, 130, 0.0006),
        ],
        "Claude Haiku + few_shot": [
            ("bench_001", 0.7, 480, 165, 155, 0.0008),
            ("bench_002", 0.8, 470, 160, 150, 0.0007),
            ("bench_003", 0.7, 500, 168, 160, 0.0008),
            ("bench_004", 0.6, 475, 162, 152, 0.0007),
            ("bench_005", 0.7, 490, 164, 154, 0.0008),
        ],
        "Claude Haiku + chain_of_thought": [
            ("bench_001", 0.8, 560, 175, 200, 0.0009),
            ("bench_002", 0.8, 550, 170, 195, 0.0009),
            ("bench_003", 0.7, 580, 178, 210, 0.0010),
            ("bench_004", 0.7, 555, 172, 198, 0.0009),
            ("bench_005", 0.7, 570, 174, 202, 0.0009),
        ],
        "GPT-4.1 mini + zero_shot": [
            ("bench_001", 0.7, 780, 130, 160, 0.0003),
            ("bench_002", 0.7, 760, 125, 155, 0.0003),
            ("bench_003", 0.6, 800, 135, 165, 0.0003),
            ("bench_004", 0.5, 770, 128, 158, 0.0003),
            ("bench_005", 0.6, 790, 126, 156, 0.0003),
        ],
        "GPT-4.1 mini + few_shot": [
            ("bench_001", 0.8, 850, 170, 180, 0.0004),
            ("bench_002", 0.9, 840, 165, 175, 0.0003),
            ("bench_003", 0.8, 880, 175, 185, 0.0004),
            ("bench_004", 0.7, 845, 168, 178, 0.0004),
            ("bench_005", 0.8, 860, 166, 176, 0.0004),
        ],
        "GPT-4.1 mini + chain_of_thought": [
            ("bench_001", 0.8, 1000, 180, 230, 0.0004),
            ("bench_002", 0.9, 980, 175, 225, 0.0004),
            ("bench_003", 0.8, 1020, 185, 240, 0.0005),
            ("bench_004", 0.8, 990, 178, 228, 0.0004),
            ("bench_005", 0.8, 1010, 176, 232, 0.0004),
        ],
    }

    results: dict[str, list[BenchmarkResult]] = {}
    for config_name, tasks in sim_data.items():
        results[config_name] = [
            BenchmarkResult(
                task_id=tid,
                config_name=config_name,
                answer=f"Simulated answer for {tid} with {config_name}.",
                keyword_score=score,
                latency_ms=lat,
                input_tokens=inp,
                output_tokens=out,
                cost_usd=cost,
                tool_calls=1,
            )
            for tid, score, lat, inp, out, cost in tasks
        ]
    return results


SIMULATED_SUITE_RESULTS = _build_simulated_results()

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
# Benchmark suite class
# ---------------------------------------------------------------------------


class BenchmarkSuite:
    """Full benchmark suite with configuration matrix and Pareto analysis."""

    def __init__(self) -> None:
        self.anthropic_tracker = AnthropicTokenTracker()
        self.openai_tracker = OpenAITokenTracker()

    def build_config_matrix(
        self, models: list[ModelConfig], prompts: dict[str, str]
    ) -> list[BenchmarkConfig]:
        """Build every model x prompt combination."""
        configs: list[BenchmarkConfig] = []
        for model in models:
            for prompt_name, system_prompt in prompts.items():
                name = f"{model.name} + {prompt_name}"
                configs.append(BenchmarkConfig(name, model, prompt_name, system_prompt))
        logger.info(
            "Built %d configurations (%d models x %d prompts)",
            len(configs),
            len(models),
            len(prompts),
        )
        return configs

    def _score_answer(self, answer: str, expected_keywords: list[str]) -> float:
        """Score an answer based on expected keyword coverage."""
        answer_lower = answer.lower()
        found = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
        return found / len(expected_keywords) if expected_keywords else 1.0

    def _run_anthropic(self, task: dict, config: BenchmarkConfig) -> BenchmarkResult:
        """Run a task using the Anthropic API."""
        client = anthropic.Anthropic()
        messages: list[dict[str, Any]] = [{"role": "user", "content": task["question"]}]
        tool_call_count = 0

        start = time.perf_counter()
        while True:
            response = client.messages.create(
                model=config.model.model_id,
                max_tokens=1024,
                system=config.system_prompt,
                tools=TOOLS_ANTHROPIC,
                messages=messages,
            )
            self.anthropic_tracker.track(response.usage)

            if response.stop_reason != "tool_use":
                answer = "".join(b.text for b in response.content if hasattr(b, "text"))
                break

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
        inp = response.usage.input_tokens
        out = response.usage.output_tokens
        cost = (
            inp * config.model.cost_per_input_token + out * config.model.cost_per_output_token
        ) / 1_000_000

        return BenchmarkResult(
            task_id=task["id"],
            config_name=config.name,
            answer=answer,
            keyword_score=self._score_answer(answer, task["expected_keywords"]),
            latency_ms=latency_ms,
            input_tokens=inp,
            output_tokens=out,
            cost_usd=cost,
            tool_calls=tool_call_count,
        )

    def _run_openai(self, task: dict, config: BenchmarkConfig) -> BenchmarkResult:
        """Run a task using the OpenAI API."""
        client = openai.OpenAI()
        messages: list[dict[str, Any]] = [{"role": "user", "content": task["question"]}]
        tool_call_count = 0

        start = time.perf_counter()
        while True:
            response = client.responses.create(
                model=config.model.model_id,
                instructions=config.system_prompt,
                max_output_tokens=1024,
                tools=TOOLS_OPENAI,
                input=messages,
            )
            self.openai_tracker.track(response.usage)

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                answer = response.output_text or ""
                break

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
        inp = response.usage.input_tokens
        out = response.usage.output_tokens
        cost = (
            inp * config.model.cost_per_input_token + out * config.model.cost_per_output_token
        ) / 1_000_000

        return BenchmarkResult(
            task_id=task["id"],
            config_name=config.name,
            answer=answer,
            keyword_score=self._score_answer(answer, task["expected_keywords"]),
            latency_ms=latency_ms,
            input_tokens=inp,
            output_tokens=out,
            cost_usd=cost,
            tool_calls=tool_call_count,
        )

    def run_suite(
        self,
        configs: list[BenchmarkConfig],
        tasks: list[dict],
        num_trials: int = 1,
    ) -> dict[str, list[BenchmarkResult]]:
        """Run the full benchmark suite across all configurations and tasks."""
        all_results: dict[str, list[BenchmarkResult]] = {}

        for config in configs:
            logger.info("Config: %s", config.name)
            config_results: list[BenchmarkResult] = []

            for trial in range(num_trials):
                for task in tasks:
                    logger.info("  Trial %d, Task %s", trial + 1, task["id"])
                    try:
                        if config.model.provider == "anthropic":
                            result = self._run_anthropic(task, config)
                        elif config.model.provider == "openai":
                            result = self._run_openai(task, config)
                        else:
                            logger.error("Unknown provider: %s", config.model.provider)
                            continue
                        config_results.append(result)
                    except Exception as e:
                        logger.error("    Error: %s", e)

            all_results[config.name] = config_results

        return all_results

    def compute_summary(self, results: dict[str, list[BenchmarkResult]]) -> list[dict[str, Any]]:
        """Compute aggregate statistics per configuration."""
        summaries: list[dict[str, Any]] = []
        for config_name, res_list in results.items():
            n = len(res_list)
            if n == 0:
                continue
            summaries.append(
                {
                    "config": config_name,
                    "accuracy": sum(r.keyword_score for r in res_list) / n,
                    "avg_latency_ms": sum(r.latency_ms for r in res_list) / n,
                    "avg_tokens": sum(r.input_tokens + r.output_tokens for r in res_list) / n,
                    "avg_cost": sum(r.cost_usd for r in res_list) / n,
                    "total_cost": sum(r.cost_usd for r in res_list),
                    "tasks": n,
                }
            )
        return summaries

    def find_pareto_optimal(self, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Find Pareto-optimal configurations (not dominated on accuracy vs cost)."""
        pareto: list[dict[str, Any]] = []

        for candidate in summaries:
            dominated = False
            for other in summaries:
                if other["config"] == candidate["config"]:
                    continue
                # "other" dominates "candidate" if it is at least as good on all dimensions
                # and strictly better on at least one
                better_or_equal_acc = other["accuracy"] >= candidate["accuracy"]
                better_or_equal_cost = other["avg_cost"] <= candidate["avg_cost"]
                strictly_better = (
                    other["accuracy"] > candidate["accuracy"]
                    or other["avg_cost"] < candidate["avg_cost"]
                )
                if better_or_equal_acc and better_or_equal_cost and strictly_better:
                    dominated = True
                    break

            if not dominated:
                pareto.append(candidate)

        logger.info(
            "Pareto-optimal: %d of %d configs",
            len(pareto),
            len(summaries),
        )
        return pareto

    def generate_report(self, summaries: list[dict[str, Any]], pareto: list[dict[str, Any]]) -> str:
        """Generate a text summary report of the benchmark results."""
        lines: list[str] = ["BENCHMARK REPORT", "=" * 60, ""]

        # Overall stats
        lines.append(f"Configurations tested: {len(summaries)}")
        lines.append(f"Pareto-optimal configs: {len(pareto)}")
        lines.append("")

        # Best on each dimension
        best_acc = max(summaries, key=lambda s: s["accuracy"])
        best_cost = min(summaries, key=lambda s: s["avg_cost"])
        best_lat = min(summaries, key=lambda s: s["avg_latency_ms"])
        lines.append("Best by dimension:")
        lines.append(f"  Accuracy: {best_acc['config']} ({best_acc['accuracy']:.0%})")
        lines.append(f"  Cost:     {best_cost['config']} (${best_cost['avg_cost']:.4f})")
        lines.append(f"  Latency:  {best_lat['config']} ({best_lat['avg_latency_ms']:.0f}ms)")
        lines.append("")

        # Pareto set
        lines.append("Pareto-optimal configurations:")
        for p in pareto:
            lines.append(
                f"  {p['config']}: accuracy={p['accuracy']:.0%}, "
                f"cost=${p['avg_cost']:.4f}, latency={p['avg_latency_ms']:.0f}ms"
            )
        lines.append("")

        # Recommendations
        lines.append("Recommendations:")
        if pareto:
            cheapest_pareto = min(pareto, key=lambda p: p["avg_cost"])
            best_pareto = max(pareto, key=lambda p: p["accuracy"])
            lines.append(f"  Budget-friendly: {cheapest_pareto['config']}")
            lines.append(f"  Best quality:    {best_pareto['config']}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run full benchmark suite with matrix comparison and Pareto analysis."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]Full Benchmark Suite[/bold cyan]\n\n"
            "Model x Prompt configuration matrix with Pareto analysis.\n"
            "Identifies non-dominated configurations across accuracy and cost.",
            title="Benchmark Tutorial 3",
        )
    )

    # Determine mode
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    live_mode = has_anthropic and has_openai

    suite = BenchmarkSuite()
    configs = suite.build_config_matrix(MODEL_CONFIGS, PROMPT_STRATEGIES)

    console.print(
        f"Configuration matrix: {len(MODEL_CONFIGS)} models x "
        f"{len(PROMPT_STRATEGIES)} prompts = {len(configs)} configs\n"
    )

    if live_mode:
        console.print("[green]API keys found — running live benchmark suite[/green]\n")
        results = suite.run_suite(configs, BENCHMARK_TASKS)
    else:
        console.print("[yellow]API keys missing — using simulated results for demo[/yellow]\n")
        results = SIMULATED_SUITE_RESULTS

    # Compute summaries
    summaries = suite.compute_summary(results)
    pareto = suite.find_pareto_optimal(summaries)

    # Full matrix results table
    matrix_table = Table(title="Configuration Matrix Results", show_lines=True)
    matrix_table.add_column("Configuration", style="bold", width=32)
    matrix_table.add_column("Accuracy", justify="center", width=10)
    matrix_table.add_column("Avg Latency", justify="right", width=12)
    matrix_table.add_column("Avg Tokens", justify="right", width=12)
    matrix_table.add_column("Avg Cost", justify="right", width=10)
    matrix_table.add_column("Pareto", justify="center", width=8)

    pareto_names = {p["config"] for p in pareto}
    for s in summaries:
        acc = s["accuracy"]
        acc_color = "green" if acc >= 0.8 else ("yellow" if acc >= 0.6 else "red")
        is_pareto = "yes" if s["config"] in pareto_names else ""
        pareto_style = "[bold green]yes[/bold green]" if is_pareto else "[dim]-[/dim]"
        matrix_table.add_row(
            s["config"],
            f"[{acc_color}]{acc:.0%}[/{acc_color}]",
            f"{s['avg_latency_ms']:.0f}ms",
            f"{s['avg_tokens']:.0f}",
            f"${s['avg_cost']:.4f}",
            pareto_style,
        )

    console.print(matrix_table)
    console.print()

    # Pareto-optimal configurations panel
    pareto_lines: list[str] = []
    for p in pareto:
        pareto_lines.append(
            f"  [bold]{p['config']}[/bold]: "
            f"accuracy={p['accuracy']:.0%}, "
            f"cost=${p['avg_cost']:.4f}, "
            f"latency={p['avg_latency_ms']:.0f}ms"
        )
    console.print(
        Panel(
            "\n".join(pareto_lines) if pareto_lines else "No Pareto-optimal configs found.",
            title="Pareto-Optimal Configurations",
            subtitle="Not dominated on accuracy vs cost",
        )
    )

    # Accuracy vs Cost scatter (text-based)
    console.print("\n[bold]Accuracy vs Cost (text plot)[/bold]")
    sorted_by_cost = sorted(summaries, key=lambda s: s["avg_cost"])
    for s in sorted_by_cost:
        bar_len = int(s["accuracy"] * 30)
        bar = "#" * bar_len + "." * (30 - bar_len)
        pareto_marker = " *" if s["config"] in pareto_names else ""
        console.print(
            f"  ${s['avg_cost']:.4f} |{bar}| {s['accuracy']:.0%}  "
            f"[dim]{s['config']}[/dim]{pareto_marker}"
        )
    console.print("  [dim](* = Pareto-optimal)[/dim]")

    # Report
    report = suite.generate_report(summaries, pareto)
    console.print()
    console.print(Panel(report, title="Benchmark Report"))

    # Token usage (live mode)
    if live_mode:
        console.print()
        suite.anthropic_tracker.report()
        suite.openai_tracker.report()


if __name__ == "__main__":
    main()
