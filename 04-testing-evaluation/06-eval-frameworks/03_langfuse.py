"""
Langfuse — Tracing and Evaluation Platform

Demonstrates how to use Langfuse for agent observability and evaluation. Langfuse
provides tracing (hierarchical spans), scoring (numeric, categorical, boolean),
and experiment tracking — all as an open-source, self-hostable platform.

This script:
1. Shows the decorator-based tracing pattern (@observe)
2. Demonstrates programmatic scoring of traces
3. Runs a mini evaluation experiment with dataset items
4. Works in simulated mode without a Langfuse server

Install: pip install langfuse
Requires: LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_BASE_URL
Or self-host: docker compose up (from langfuse repo)
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any

from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shared.knowledge_base import EVAL_TASKS, get_agent_response

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Simulated Langfuse trace collector (for demo without a Langfuse server)
# ---------------------------------------------------------------------------


@dataclass
class SimulatedSpan:
    """A simulated Langfuse observation/span."""

    name: str
    span_type: str
    start_time: float = 0.0
    end_time: float = 0.0
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    scores: list[dict[str, Any]] = field(default_factory=list)
    children: list["SimulatedSpan"] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


@dataclass
class SimulatedTrace:
    """A simulated Langfuse trace with scoring."""

    trace_id: str
    name: str
    spans: list[SimulatedSpan] = field(default_factory=list)
    scores: list[dict[str, Any]] = field(default_factory=list)


class SimulatedLangfuse:
    """Simulates Langfuse tracing and scoring for demo purposes."""

    def __init__(self) -> None:
        self.traces: list[SimulatedTrace] = []
        self._current_trace: SimulatedTrace | None = None

    def start_trace(self, name: str, trace_id: str) -> SimulatedTrace:
        """Start a new trace."""
        trace = SimulatedTrace(trace_id=trace_id, name=name)
        self.traces.append(trace)
        self._current_trace = trace
        return trace

    def start_span(self, name: str, span_type: str = "span") -> SimulatedSpan:
        """Start a new span within the current trace."""
        span = SimulatedSpan(name=name, span_type=span_type, start_time=time.perf_counter())
        if self._current_trace:
            self._current_trace.spans.append(span)
        return span

    def end_span(self, span: SimulatedSpan, output: dict[str, Any] | None = None) -> None:
        """End a span and record output."""
        span.end_time = time.perf_counter()
        if output:
            span.output_data = output

    def score_trace(
        self,
        trace: SimulatedTrace,
        name: str,
        value: float | str | bool,
        data_type: str = "NUMERIC",
        comment: str = "",
    ) -> None:
        """Add a score to a trace (mirrors langfuse.create_score)."""
        trace.scores.append(
            {
                "name": name,
                "value": value,
                "data_type": data_type,
                "comment": comment,
            }
        )


# ---------------------------------------------------------------------------
# Evaluation with tracing and scoring
# ---------------------------------------------------------------------------


def run_traced_eval(
    langfuse_client: SimulatedLangfuse,
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run evaluation tasks with Langfuse-style tracing and scoring."""
    results: list[dict[str, Any]] = []

    for task in tasks:
        # Start a trace for this eval task
        trace = langfuse_client.start_trace(
            name=f"eval_{task['id']}",
            trace_id=f"trace_{task['id']}",
        )

        # Span: agent execution
        agent_span = langfuse_client.start_span("agent_call", span_type="generation")
        agent_span.input_data = {"question": task["question"]}

        response = get_agent_response(task["id"])

        langfuse_client.end_span(agent_span, output={"answer": response["answer"]})

        # Span: grading
        grading_span = langfuse_client.start_span("grading", span_type="span")

        # Score: keyword coverage (NUMERIC)
        answer_lower = response["answer"].lower()
        keywords = task["expected_keywords"]
        if keywords:
            found = sum(1 for kw in keywords if kw.lower() in answer_lower)
            keyword_score = found / len(keywords)
        else:
            has_refusal = "unable" in answer_lower or "no relevant" in answer_lower
            keyword_score = 1.0 if has_refusal else 0.0

        langfuse_client.score_trace(
            trace,
            name="keyword_coverage",
            value=keyword_score,
            data_type="NUMERIC",
            comment=f"Found {found if keywords else 'N/A'}/{len(keywords)} keywords",
        )

        # Score: source grounding (BOOLEAN)
        expected_sources = task.get("expected_source_ids", [])
        if expected_sources:
            all_cited = all(sid in response["answer"] for sid in expected_sources)
        else:
            all_cited = "unable" in answer_lower or "no relevant" in answer_lower
        langfuse_client.score_trace(
            trace,
            name="source_grounded",
            value=all_cited,
            data_type="BOOLEAN",
            comment="All expected sources cited" if all_cited else "Missing source citations",
        )

        # Score: quality category (CATEGORICAL)
        if keyword_score >= 0.8 and all_cited:
            quality = "excellent"
        elif keyword_score >= 0.5:
            quality = "acceptable"
        else:
            quality = "poor"
        langfuse_client.score_trace(
            trace,
            name="quality_tier",
            value=quality,
            data_type="CATEGORICAL",
            comment=f"keyword={keyword_score:.0%}, grounded={all_cited}",
        )

        langfuse_client.end_span(grading_span)

        results.append(
            {
                "task_id": task["id"],
                "trace_id": trace.trace_id,
                "keyword_score": keyword_score,
                "grounded": all_cited,
                "quality": quality,
                "duration_ms": sum(s.duration_ms for s in trace.spans),
            }
        )

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run Langfuse-style traced evaluation of the research assistant."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]Langfuse — Tracing & Evaluation Platform[/bold cyan]\n\n"
            "Demonstrates Langfuse patterns for agent evaluation:\n"
            "  - Decorator-based tracing (@observe)\n"
            "  - Programmatic scoring (NUMERIC, BOOLEAN, CATEGORICAL)\n"
            "  - Experiment tracking with datasets\n\n"
            "Open source, self-hostable. Install: pip install langfuse",
            title="03 - Langfuse",
        )
    )

    # Check for Langfuse SDK and credentials
    has_langfuse = False
    try:
        import langfuse  # noqa: F401

        has_langfuse = True
    except ImportError:
        pass

    has_langfuse_keys = bool(
        os.environ.get("LANGFUSE_SECRET_KEY") and os.environ.get("LANGFUSE_PUBLIC_KEY")
    )

    if has_langfuse and has_langfuse_keys:
        console.print("[green]Langfuse SDK + keys found — traces will be sent to server[/green]")
    elif has_langfuse:
        console.print(
            "[yellow]Langfuse SDK installed but no keys — running simulated mode[/yellow]"
        )
    else:
        console.print("[yellow]Langfuse not installed — running simulated demo[/yellow]")
    console.print()

    # Run evaluation with simulated Langfuse client
    # In production, replace SimulatedLangfuse with the real Langfuse SDK
    langfuse_client = SimulatedLangfuse()
    results = run_traced_eval(langfuse_client, EVAL_TASKS)

    # Results table
    table = Table(title="Langfuse Traced Evaluation Results", show_lines=True)
    table.add_column("Task", style="cyan", width=12)
    table.add_column("Trace ID", width=16)
    table.add_column("Keywords", width=10, justify="center")
    table.add_column("Grounded", width=10, justify="center")
    table.add_column("Quality", width=12, justify="center")
    table.add_column("Duration", width=10, justify="right")

    for r in results:
        kw_color = "green" if r["keyword_score"] >= 0.7 else "yellow"
        grounded_str = "[green]True[/green]" if r["grounded"] else "[red]False[/red]"
        quality_color = {
            "excellent": "green",
            "acceptable": "yellow",
            "poor": "red",
        }.get(r["quality"], "dim")

        table.add_row(
            r["task_id"],
            r["trace_id"],
            f"[{kw_color}]{r['keyword_score']:.0%}[/{kw_color}]",
            grounded_str,
            f"[{quality_color}]{r['quality']}[/{quality_color}]",
            f"{r['duration_ms']:.1f}ms",
        )

    console.print(table)

    # Trace summary
    console.print(
        f"\n[bold]Traces collected:[/bold] {len(langfuse_client.traces)}\n"
        f"[bold]Total scores:[/bold] "
        f"{sum(len(t.scores) for t in langfuse_client.traces)}\n"
        f"[bold]Total spans:[/bold] "
        f"{sum(len(t.spans) for t in langfuse_client.traces)}"
    )

    # Score type breakdown
    score_types = {"NUMERIC": 0, "BOOLEAN": 0, "CATEGORICAL": 0}
    for trace in langfuse_client.traces:
        for score in trace.scores:
            score_types[score["data_type"]] = score_types.get(score["data_type"], 0) + 1

    console.print("\n[bold]Score types used:[/bold]")
    for dtype, count in score_types.items():
        console.print(f"  {dtype}: {count}")

    # Show Langfuse code patterns
    console.print("\n[bold]Langfuse SDK Patterns:[/bold]\n")
    from rich.syntax import Syntax

    decorator_code = (
        "from langfuse import observe, get_client\n\n"
        "@observe()  # Automatically creates a trace\n"
        "def my_agent(question: str) -> str:\n"
        "    result = search_and_answer(question)\n"
        "    return result\n\n"
        '@observe(name="llm-call", as_type="generation")\n'
        "def search_and_answer(question: str) -> str:\n"
        "    # Nested spans are captured automatically\n"
        "    return call_llm(question)\n"
    )
    console.print(Syntax(decorator_code, "python", theme="monokai", line_numbers=True))

    scoring_code = (
        "langfuse = get_client()\n\n"
        "# Score after execution\n"
        "langfuse.create_score(\n"
        "    trace_id=trace_id,\n"
        '    name="correctness",\n'
        "    value=0.95,\n"
        '    data_type="NUMERIC",\n'
        '    comment="Factually accurate",\n'
        ")\n"
    )
    console.print(Syntax(scoring_code, "python", theme="monokai", line_numbers=True))


if __name__ == "__main__":
    main()
