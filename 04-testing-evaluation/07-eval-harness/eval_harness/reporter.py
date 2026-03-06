"""Rich terminal report generator for the eval harness."""

import logging
from collections import defaultdict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from eval_harness.models import BenchmarkEntry, EvalReport, EvalResult, SafetyResult

logger = logging.getLogger(__name__)


class EvalReporter:
    """Generates Rich terminal reports from eval results."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def print_report(self, report: EvalReport) -> None:
        """Print the complete evaluation report."""
        self.print_summary_panel(report)
        self.console.print()
        self.print_quality_table(report.eval_results)
        self.console.print()
        self.print_safety_table(report.safety_results)
        self.console.print()
        self.print_benchmark_table(report.benchmark_entries)

    def print_quality_table(self, results: list[EvalResult]) -> None:
        """Print detailed quality eval results as a table."""
        table = Table(title="Quality Evaluation Results", show_lines=True)
        table.add_column("Task", style="cyan", width=10)
        table.add_column("Pass Rate", width=10)
        table.add_column("Avg Score", width=10)
        table.add_column("Keyword", width=20)
        table.add_column("Citation", width=20)
        table.add_column("Tool Call", width=20)

        for result in results:
            # Extract individual grader scores
            grader_map = {gs.grader_name: gs for gs in result.grader_scores}

            def fmt_grader(name: str, gm: dict = grader_map) -> str:
                gs = gm.get(name)
                if not gs:
                    return "[dim]N/A[/dim]"
                icon = "[green]PASS[/green]" if gs.passed else "[red]FAIL[/red]"
                return f"{icon} ({gs.score:.0%})"

            pass_style = "green" if result.pass_rate >= 0.5 else "red"
            table.add_row(
                result.task_id,
                f"[{pass_style}]{result.pass_rate:.0%}[/{pass_style}]",
                f"{result.avg_score:.2f}",
                fmt_grader("keyword"),
                fmt_grader("citation"),
                fmt_grader("tool_call"),
            )

        self.console.print(table)

    def print_safety_table(self, results: list[SafetyResult]) -> None:
        """Print safety test results as a table."""
        if not results:
            return

        table = Table(title="Safety Test Results", show_lines=True)
        table.add_column("ID", style="dim", width=8)
        table.add_column("Attack", width=28)
        table.add_column("Category", width=18)
        table.add_column("Severity", width=10)
        table.add_column("Result", width=10)

        for result in results:
            severity_style = {
                "high": "red",
                "critical": "red bold",
                "medium": "yellow",
                "low": "green",
            }.get(result.severity, "white")

            result_style = "green" if result.blocked else "red bold"
            result_text = "BLOCKED" if result.blocked else "BYPASSED"

            table.add_row(
                result.attack_id,
                result.attack_name,
                result.category,
                f"[{severity_style}]{result.severity}[/{severity_style}]",
                f"[{result_style}]{result_text}[/{result_style}]",
            )

        self.console.print(table)

    def print_benchmark_table(self, entries: list[BenchmarkEntry]) -> None:
        """Print benchmark results aggregated by model config."""
        if not entries:
            return

        # Aggregate per config
        config_data: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: {"accuracy": [], "latency": [], "cost": [], "tokens": []}
        )
        for entry in entries:
            config_data[entry.config_name]["accuracy"].append(entry.accuracy)
            config_data[entry.config_name]["latency"].append(entry.latency_ms)
            config_data[entry.config_name]["cost"].append(entry.cost_usd)
            config_data[entry.config_name]["tokens"].append(float(entry.tokens))

        table = Table(title="Benchmark Results (per model config)", show_lines=True)
        table.add_column("Config", style="cyan", width=16)
        table.add_column("Avg Accuracy", width=14)
        table.add_column("Avg Latency", width=14)
        table.add_column("Total Cost", width=14)
        table.add_column("Avg Tokens", width=14)

        for config_name, data in config_data.items():
            avg_acc = sum(data["accuracy"]) / len(data["accuracy"])
            avg_lat = sum(data["latency"]) / len(data["latency"])
            total_cost = sum(data["cost"])
            avg_tok = sum(data["tokens"]) / len(data["tokens"])

            acc_style = "green" if avg_acc >= 0.8 else ("yellow" if avg_acc >= 0.6 else "red")
            table.add_row(
                config_name,
                f"[{acc_style}]{avg_acc:.1%}[/{acc_style}]",
                f"{avg_lat:.0f}ms",
                f"${total_cost:.4f}",
                f"{avg_tok:.0f}",
            )

        self.console.print(table)

    def print_summary_panel(self, report: EvalReport) -> None:
        """Print the final summary panel."""
        # Quality stats
        total_tasks = len(report.eval_results)
        passed_tasks = sum(1 for r in report.eval_results if r.pass_rate >= 0.5)
        quality_pct = (passed_tasks / total_tasks * 100) if total_tasks else 0

        # Safety stats
        total_attacks = len(report.safety_results)
        blocked_attacks = sum(1 for r in report.safety_results if r.blocked)
        safety_pct = (blocked_attacks / total_attacks * 100) if total_attacks else 0

        # Latency
        avg_latency = report.total_latency_ms / total_tasks if total_tasks else 0

        # Build summary text
        quality_style = "green" if quality_pct >= 80 else ("yellow" if quality_pct >= 60 else "red")
        safety_style = "green" if safety_pct >= 80 else ("yellow" if safety_pct >= 60 else "red")

        summary = (
            f"  Quality Evals        "
            f"[{quality_style}]{passed_tasks}/{total_tasks} tasks passed "
            f"({quality_pct:.1f}%)[/{quality_style}]\n"
            f"  Safety Score         "
            f"[{safety_style}]{blocked_attacks}/{total_attacks} attacks blocked "
            f"({safety_pct:.1f}%)[/{safety_style}]\n"
            f"  Avg Latency          {avg_latency / 1000:.1f}s per task\n"
            f"  Total Cost           ${report.total_cost_usd:.4f}"
        )

        self.console.print(
            Panel(
                summary,
                title=f"Eval Report: {report.agent_name}",
                border_style="bold cyan",
            )
        )
