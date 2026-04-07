"""Model benchmarking with Pareto analysis for the eval harness."""

import logging
import random
from typing import Any

from eval_harness.models import BenchmarkEntry, EvalTask

logger = logging.getLogger(__name__)

# Simulated model configurations with realistic performance characteristics
DEFAULT_CONFIGS: list[dict[str, Any]] = [
    {
        "name": "claude-haiku",
        "model": "claude-3-5-haiku-20241022",
        "avg_latency_ms": 600.0,
        "cost_per_1k_input": 0.001,
        "cost_per_1k_output": 0.005,
        "accuracy_modifier": 0.75,
    },
    {
        "name": "claude-sonnet",
        "model": "claude-sonnet-4-5-20250929",
        "avg_latency_ms": 1500.0,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "accuracy_modifier": 0.90,
    },
    {
        "name": "claude-opus",
        "model": "claude-opus-4-0-20250514",
        "avg_latency_ms": 3000.0,
        "cost_per_1k_input": 0.015,
        "cost_per_1k_output": 0.075,
        "accuracy_modifier": 0.95,
    },
]


class BenchmarkRunner:
    """Runs benchmarks across model configurations."""

    def __init__(self, configs: list[dict[str, Any]] | None = None) -> None:
        self.configs = configs or DEFAULT_CONFIGS

    def run_benchmark(
        self, tasks: list[EvalTask], configs: list[dict[str, Any]] | None = None
    ) -> list[BenchmarkEntry]:
        """Run simulated benchmarks across model configurations and tasks."""
        configs = configs or self.configs
        entries: list[BenchmarkEntry] = []

        for config in configs:
            logger.info("Benchmarking config: %s", config["name"])
            for task in tasks:
                entry = self._simulate_benchmark(task, config)
                entries.append(entry)

        logger.info(
            "Benchmark complete: %d entries across %d configs",
            len(entries),
            len(configs),
        )
        return entries

    def _simulate_benchmark(self, task: EvalTask, config: dict[str, Any]) -> BenchmarkEntry:
        """Simulate a benchmark run for one task + config combination."""
        # Simulate latency with variance
        base_latency = config["avg_latency_ms"]
        latency = base_latency + random.uniform(-base_latency * 0.2, base_latency * 0.2)

        # Simulate accuracy based on task difficulty and model capability
        difficulty_modifier = {"easy": 1.0, "medium": 0.85, "hard": 0.7}.get(task.difficulty, 0.85)
        accuracy = min(1.0, config["accuracy_modifier"] * difficulty_modifier)

        # Simulate token usage
        input_tokens = random.randint(200, 400)
        output_tokens = random.randint(80, 200)
        total_tokens = input_tokens + output_tokens

        # Calculate cost
        cost = (
            input_tokens / 1000 * config["cost_per_1k_input"]
            + output_tokens / 1000 * config["cost_per_1k_output"]
        )

        return BenchmarkEntry(
            config_name=config["name"],
            task_id=task.id,
            accuracy=round(accuracy, 3),
            latency_ms=round(latency, 1),
            cost_usd=round(cost, 6),
            tokens=total_tokens,
        )

    def find_pareto_optimal(self, entries: list[BenchmarkEntry]) -> list[str]:
        """Find Pareto-optimal configs balancing accuracy, latency, and cost."""
        # Aggregate metrics per config
        config_metrics: dict[str, dict[str, float]] = {}
        for entry in entries:
            if entry.config_name not in config_metrics:
                config_metrics[entry.config_name] = {
                    "accuracy_sum": 0.0,
                    "latency_sum": 0.0,
                    "cost_sum": 0.0,
                    "count": 0,
                }
            metrics = config_metrics[entry.config_name]
            metrics["accuracy_sum"] += entry.accuracy
            metrics["latency_sum"] += entry.latency_ms
            metrics["cost_sum"] += entry.cost_usd
            metrics["count"] += 1

        # Compute averages
        averages: dict[str, dict[str, float]] = {}
        for name, metrics in config_metrics.items():
            count = metrics["count"]
            averages[name] = {
                "accuracy": metrics["accuracy_sum"] / count,
                "latency": metrics["latency_sum"] / count,
                "cost": metrics["cost_sum"] / count,
            }

        # Find Pareto-optimal: a config is dominated if another config is better on all axes
        pareto: list[str] = []
        config_names = list(averages.keys())

        for name in config_names:
            dominated = False
            for other_name in config_names:
                if name == other_name:
                    continue
                other = averages[other_name]
                current = averages[name]
                # Other dominates if it has higher accuracy, lower latency, and lower cost
                if (
                    other["accuracy"] >= current["accuracy"]
                    and other["latency"] <= current["latency"]
                    and other["cost"] <= current["cost"]
                    and (
                        other["accuracy"] > current["accuracy"]
                        or other["latency"] < current["latency"]
                        or other["cost"] < current["cost"]
                    )
                ):
                    dominated = True
                    break
            if not dominated:
                pareto.append(name)

        logger.info("Pareto-optimal configs: %s", pareto)
        return pareto
