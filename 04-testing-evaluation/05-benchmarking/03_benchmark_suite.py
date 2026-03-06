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
from typing import Any

import anthropic
import openai
from common import AnthropicTokenTracker, OpenAITokenTracker, setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shared.knowledge_base import (
    BENCHMARK_TASKS,
    TOOLS_ANTHROPIC,
    TOOLS_OPENAI,
    score_answer,
    search_knowledge_base,
)
from shared.models import MODEL_CONFIGS, BenchmarkConfig, BenchmarkResult, ModelConfig

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

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
            keyword_score=score_answer(answer, task["expected_keywords"]),
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
            keyword_score=score_answer(answer, task["expected_keywords"]),
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
