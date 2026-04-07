"""
Prompt Strategy Comparison Benchmark

Benchmarks three prompt strategies (zero-shot, few-shot, chain-of-thought) on the same model
and tasks. Measures how prompt engineering affects accuracy, verbosity, and cost.
Supports both live API calls and a simulated mode for demo without API keys.
"""

import json
import os
import time
from typing import Any

import anthropic
from common import AnthropicTokenTracker, setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shared.knowledge_base import (
    BENCHMARK_TASKS,
    TOOLS_ANTHROPIC,
    score_answer,
    search_knowledge_base,
)
from shared.models import BenchmarkResult

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Prompt strategies — the core variable under test
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

# Default model for prompt comparison — isolate the prompt variable
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
COST_PER_INPUT = 3.0  # dollars per 1M tokens
COST_PER_OUTPUT = 15.0  # dollars per 1M tokens

# ---------------------------------------------------------------------------
# Simulated results for demo mode
# ---------------------------------------------------------------------------

SIMULATED_RESULTS: dict[str, list[BenchmarkResult]] = {
    "zero_shot": [
        BenchmarkResult(
            "bench_001",
            "zero_shot",
            "Microservices provide scalability and fault isolation (doc_001).",
            0.7,
            1100,
            140,
            120,
            0.0022,
            1,
        ),
        BenchmarkResult(
            "bench_002",
            "zero_shot",
            "Use nouns for endpoints and HTTP methods (doc_002).",
            0.7,
            1050,
            135,
            115,
            0.0021,
            1,
        ),
        BenchmarkResult(
            "bench_003",
            "zero_shot",
            "B-tree indexes improve query performance (doc_003).",
            0.6,
            1120,
            142,
            118,
            0.0022,
            1,
        ),
        BenchmarkResult(
            "bench_004",
            "zero_shot",
            "Authentication is identity verification, authorization controls access (doc_004).",
            0.5,
            1080,
            138,
            122,
            0.0022,
            1,
        ),
        BenchmarkResult(
            "bench_005",
            "zero_shot",
            "CI/CD includes automated testing and continuous deployment (doc_005).",
            0.6,
            1090,
            136,
            116,
            0.0022,
            1,
        ),
    ],
    "few_shot": [
        BenchmarkResult(
            "bench_001",
            "few_shot",
            (
                "Microservices architecture provides scalability, fault "
                "isolation, and independent deployment (doc_001)."
            ),
            0.9,
            1250,
            185,
            160,
            0.0030,
            1,
        ),
        BenchmarkResult(
            "bench_002",
            "few_shot",
            (
                "REST API endpoints use nouns, HTTP methods for actions, "
                "and status codes for results (doc_002)."
            ),
            1.0,
            1200,
            180,
            155,
            0.0029,
            1,
        ),
        BenchmarkResult(
            "bench_003",
            "few_shot",
            (
                "Database indexing uses B-tree indexes, composite indexes, "
                "and improves query performance (doc_003)."
            ),
            0.9,
            1280,
            188,
            162,
            0.0030,
            1,
        ),
        BenchmarkResult(
            "bench_004",
            "few_shot",
            (
                "Authentication verifies identity, authorization controls "
                "access. JWT and OAuth 2.0 are used (doc_004)."
            ),
            0.8,
            1220,
            182,
            158,
            0.0029,
            1,
        ),
        BenchmarkResult(
            "bench_005",
            "few_shot",
            (
                "Key CI/CD practices include continuous integration, "
                "automated testing, and fast feedback loops (doc_005)."
            ),
            0.9,
            1240,
            184,
            156,
            0.0029,
            1,
        ),
    ],
    "chain_of_thought": [
        BenchmarkResult(
            "bench_001",
            "chain_of_thought",
            (
                "Step 1: Searched for microservices. Step 2: Key facts "
                "- scalability, fault isolation, independent deployment. "
                "Step 3: Microservices enable independent scaling and "
                "fault isolation (doc_001)."
            ),
            0.9,
            1500,
            195,
            250,
            0.0043,
            1,
        ),
        BenchmarkResult(
            "bench_002",
            "chain_of_thought",
            (
                "Step 1: Searched for REST API. Step 2: Nouns for "
                "endpoints, HTTP methods, status codes. Step 3: REST "
                "APIs should use nouns, HTTP methods, and status codes "
                "(doc_002)."
            ),
            1.0,
            1450,
            190,
            245,
            0.0042,
            1,
        ),
        BenchmarkResult(
            "bench_003",
            "chain_of_thought",
            (
                "Step 1: Searched for indexing. Step 2: B-tree, "
                "composite, query performance. Step 3: B-tree and "
                "composite indexes improve query performance (doc_003)."
            ),
            0.9,
            1520,
            198,
            255,
            0.0044,
            1,
        ),
        BenchmarkResult(
            "bench_004",
            "chain_of_thought",
            (
                "Step 1: Searched for auth. Step 2: Identity, access, "
                "JWT, OAuth. Step 3: Authentication verifies identity "
                "while authorization controls access using JWT and "
                "OAuth (doc_004)."
            ),
            1.0,
            1480,
            192,
            248,
            0.0043,
            1,
        ),
        BenchmarkResult(
            "bench_005",
            "chain_of_thought",
            (
                "Step 1: Searched for CI/CD. Step 2: Continuous, "
                "automated, feedback. Step 3: CI/CD relies on continuous "
                "automated builds and fast feedback loops (doc_005)."
            ),
            0.9,
            1510,
            196,
            252,
            0.0044,
            1,
        ),
    ],
}

# ---------------------------------------------------------------------------
# Prompt benchmark class
# ---------------------------------------------------------------------------


class PromptBenchmark:
    """Benchmarks different prompt strategies on the same model and tasks."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self.token_tracker = AnthropicTokenTracker()

    def run_with_prompt(self, task: dict, prompt_name: str, system_prompt: str) -> BenchmarkResult:
        """Run a single task with a specific prompt strategy."""
        client = anthropic.Anthropic()
        messages: list[dict[str, Any]] = [{"role": "user", "content": task["question"]}]
        tool_call_count = 0

        start = time.perf_counter()

        while True:
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                tools=TOOLS_ANTHROPIC,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

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
        input_tok = response.usage.input_tokens
        output_tok = response.usage.output_tokens
        cost = (input_tok * COST_PER_INPUT + output_tok * COST_PER_OUTPUT) / 1_000_000

        return BenchmarkResult(
            task_id=task["id"],
            config_name=prompt_name,
            answer=answer,
            keyword_score=score_answer(answer, task["expected_keywords"]),
            latency_ms=latency_ms,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
            tool_calls=tool_call_count,
        )

    def run_comparison(self, tasks: list[dict]) -> dict[str, list[BenchmarkResult]]:
        """Run all tasks with each prompt strategy."""
        all_results: dict[str, list[BenchmarkResult]] = {}

        for prompt_name, system_prompt in PROMPT_STRATEGIES.items():
            logger.info("Running prompt strategy: %s", prompt_name)
            strategy_results: list[BenchmarkResult] = []

            for task in tasks:
                logger.info("  Task %s: %s", task["id"], task["question"][:50])
                try:
                    result = self.run_with_prompt(task, prompt_name, system_prompt)
                    strategy_results.append(result)
                    logger.info(
                        "    score=%.2f, latency=%dms, tokens=%d",
                        result.keyword_score,
                        result.latency_ms,
                        result.input_tokens + result.output_tokens,
                    )
                except Exception as e:
                    logger.error("    Error: %s", e)

            all_results[prompt_name] = strategy_results

        return all_results


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def aggregate_by_strategy(
    results: dict[str, list[BenchmarkResult]],
) -> dict[str, dict[str, float]]:
    """Compute per-strategy averages."""
    summaries: dict[str, dict[str, float]] = {}
    for strategy, res_list in results.items():
        n = len(res_list)
        if n == 0:
            continue
        summaries[strategy] = {
            "accuracy": sum(r.keyword_score for r in res_list) / n,
            "avg_latency_ms": sum(r.latency_ms for r in res_list) / n,
            "avg_output_tokens": sum(r.output_tokens for r in res_list) / n,
            "avg_cost": sum(r.cost_usd for r in res_list) / n,
            "tasks": n,
        }
    return summaries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run prompt strategy comparison and display results."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]Prompt Strategy Comparison[/bold cyan]\n\n"
            "Same model, three prompt strategies: zero-shot, few-shot, chain-of-thought.\n"
            "Measures how prompt engineering affects accuracy, verbosity, and cost.",
            title="Benchmark Tutorial 2",
        )
    )

    # Determine mode
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if has_api_key:
        console.print(
            f"[green]API key found — running live benchmark with {DEFAULT_MODEL}[/green]\n"
        )
        benchmark = PromptBenchmark()
        results = benchmark.run_comparison(BENCHMARK_TASKS)
    else:
        console.print("[yellow]No API key — using simulated results for demo[/yellow]\n")
        results = SIMULATED_RESULTS

    # Per-task detail table
    detail_table = Table(title="Per-Task Results by Prompt Strategy", show_lines=True)
    detail_table.add_column("Task", style="cyan", width=10)
    detail_table.add_column("Strategy", width=16)
    detail_table.add_column("Score", justify="center", width=7)
    detail_table.add_column("Latency", justify="right", width=9)
    detail_table.add_column("Out Tokens", justify="right", width=10)
    detail_table.add_column("Cost", justify="right", width=9)

    for strategy, res_list in results.items():
        for r in res_list:
            score_color = (
                "green"
                if r.keyword_score >= 0.8
                else ("yellow" if r.keyword_score >= 0.5 else "red")
            )
            detail_table.add_row(
                r.task_id,
                strategy,
                f"[{score_color}]{r.keyword_score:.0%}[/{score_color}]",
                f"{r.latency_ms:.0f}ms",
                str(r.output_tokens),
                f"${r.cost_usd:.4f}",
            )

    console.print(detail_table)
    console.print()

    # Summary comparison table
    summaries = aggregate_by_strategy(results)

    summary_table = Table(title="Prompt Strategy Comparison Summary", show_lines=True)
    summary_table.add_column("Strategy", style="bold", width=18)
    summary_table.add_column("Accuracy", justify="center", width=10)
    summary_table.add_column("Avg Latency", justify="right", width=12)
    summary_table.add_column("Avg Out Tokens", justify="right", width=14)
    summary_table.add_column("Avg Cost", justify="right", width=10)

    for strategy, stats in summaries.items():
        acc = stats["accuracy"]
        acc_color = "green" if acc >= 0.8 else ("yellow" if acc >= 0.6 else "red")
        summary_table.add_row(
            strategy,
            f"[{acc_color}]{acc:.0%}[/{acc_color}]",
            f"{stats['avg_latency_ms']:.0f}ms",
            f"{stats['avg_output_tokens']:.0f}",
            f"${stats['avg_cost']:.4f}",
        )

    console.print(summary_table)

    # Analysis
    console.print("\n[bold]Analysis[/bold]")
    best_acc = max(summaries.items(), key=lambda x: x[1]["accuracy"])
    cheapest = min(summaries.items(), key=lambda x: x[1]["avg_cost"])
    most_verbose = max(summaries.items(), key=lambda x: x[1]["avg_output_tokens"])
    console.print(f"  Highest accuracy:  {best_acc[0]} ({best_acc[1]['accuracy']:.0%})")
    console.print(f"  Lowest cost:       {cheapest[0]} (${cheapest[1]['avg_cost']:.4f})")
    console.print(
        f"  Most verbose:      {most_verbose[0]} "
        f"({most_verbose[1]['avg_output_tokens']:.0f} tokens)"
    )

    # Trade-off insight
    console.print(
        Panel(
            "Few-shot prompts typically improve accuracy by providing output format examples.\n"
            "Chain-of-thought increases token usage (cost) but can improve reasoning quality.\n"
            "Zero-shot is cheapest but may miss nuances. "
            "Choose based on your accuracy vs cost budget.",
            title="Key Insight",
            style="dim",
        )
    )

    # Token usage report (live mode)
    if has_api_key:
        console.print()
        benchmark.token_tracker.report()


if __name__ == "__main__":
    main()
