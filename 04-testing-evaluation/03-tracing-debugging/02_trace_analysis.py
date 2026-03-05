"""
Trace Analysis

Demonstrates how to load recorded traces and compute aggregate metrics, detect
anti-patterns, and compare traces. Works entirely offline using sample trace data —
no API keys required.

Key concepts:
- Aggregate metrics: total tokens, cost estimation, latency breakdown by span type
- Anti-pattern detection: excessive calls, repeated searches, high token usage, errors
- Trace comparison: diff two traces of the same task to spot regressions
"""

import json
from typing import Any

from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# Cost per token (approximate, for educational purposes)
COST_PER_INPUT_TOKEN = 3.0 / 1_000_000  # $3 per 1M input tokens
COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000  # $15 per 1M output tokens


# ---------------------------------------------------------------------------
# Sample traces — self-contained, no API key needed
# ---------------------------------------------------------------------------

SAMPLE_TRACE_GOOD = {
    "trace_id": "trace_good",
    "question": "What are the benefits of microservices?",
    "spans": [
        {
            "name": "answer_question",
            "span_type": "agent_step",
            "start_time": 1000.0,
            "end_time": 1003.5,
            "duration_ms": 3500.0,
            "inputs": {"question": "What are the benefits of microservices?"},
            "outputs": {"answer": "Microservices offer scalability, fault isolation..."},
            "tokens": {},
            "error": None,
            "children": [
                {
                    "name": "llm_call_1",
                    "span_type": "llm_call",
                    "start_time": 1000.1,
                    "end_time": 1001.2,
                    "duration_ms": 1100.0,
                    "inputs": {"message_count": 1},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 150, "output": 80},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_search_knowledge_base",
                    "span_type": "tool_call",
                    "start_time": 1001.2,
                    "end_time": 1001.22,
                    "duration_ms": 20.0,
                    "inputs": {
                        "tool": "search_knowledge_base",
                        "input": {"query": "microservices benefits"},
                    },
                    "outputs": {"result": "[{'id': 'doc_001'}]"},
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "llm_call_2",
                    "span_type": "llm_call",
                    "start_time": 1001.3,
                    "end_time": 1002.5,
                    "duration_ms": 1200.0,
                    "inputs": {"message_count": 3},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 280, "output": 60},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_get_document",
                    "span_type": "tool_call",
                    "start_time": 1002.5,
                    "end_time": 1002.51,
                    "duration_ms": 10.0,
                    "inputs": {"tool": "get_document", "input": {"doc_id": "doc_001"}},
                    "outputs": {"result": "{'id': 'doc_001', 'title': 'Microservices'}"},
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "llm_call_3",
                    "span_type": "llm_call",
                    "start_time": 1002.6,
                    "end_time": 1003.4,
                    "duration_ms": 800.0,
                    "inputs": {"message_count": 5},
                    "outputs": {"stop_reason": "end_turn"},
                    "tokens": {"input": 450, "output": 120},
                    "error": None,
                    "children": [],
                },
            ],
        }
    ],
}

SAMPLE_TRACE_ANTI_PATTERNS = {
    "trace_id": "trace_anti",
    "question": "Tell me about caching",
    "spans": [
        {
            "name": "answer_question",
            "span_type": "agent_step",
            "start_time": 2000.0,
            "end_time": 2018.0,
            "duration_ms": 18000.0,
            "inputs": {"question": "Tell me about caching"},
            "outputs": {"answer": "Caching is..."},
            "tokens": {},
            "error": None,
            "children": [
                {
                    "name": "llm_call_1",
                    "span_type": "llm_call",
                    "start_time": 2000.1,
                    "end_time": 2001.5,
                    "duration_ms": 1400.0,
                    "inputs": {"message_count": 1},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 200, "output": 90},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_search_knowledge_base",
                    "span_type": "tool_call",
                    "start_time": 2001.5,
                    "end_time": 2001.52,
                    "duration_ms": 20.0,
                    "inputs": {"tool": "search_knowledge_base", "input": {"query": "caching"}},
                    "outputs": {"result": "[{'id': 'doc_008'}]"},
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "llm_call_2",
                    "span_type": "llm_call",
                    "start_time": 2001.6,
                    "end_time": 2003.0,
                    "duration_ms": 1400.0,
                    "inputs": {"message_count": 3},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 350, "output": 70},
                    "error": None,
                    "children": [],
                },
                # Repeated search — same query again (anti-pattern)
                {
                    "name": "tool_search_knowledge_base",
                    "span_type": "tool_call",
                    "start_time": 2003.0,
                    "end_time": 2003.02,
                    "duration_ms": 20.0,
                    "inputs": {"tool": "search_knowledge_base", "input": {"query": "caching"}},
                    "outputs": {"result": "[{'id': 'doc_008'}]"},
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "llm_call_3",
                    "span_type": "llm_call",
                    "start_time": 2003.1,
                    "end_time": 2005.0,
                    "duration_ms": 1900.0,
                    "inputs": {"message_count": 5},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 500, "output": 100},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_get_document",
                    "span_type": "tool_call",
                    "start_time": 2005.0,
                    "end_time": 2005.01,
                    "duration_ms": 10.0,
                    "inputs": {"tool": "get_document", "input": {"doc_id": "doc_008"}},
                    "outputs": {"result": "{'id': 'doc_008'}"},
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "llm_call_4",
                    "span_type": "llm_call",
                    "start_time": 2005.1,
                    "end_time": 2007.0,
                    "duration_ms": 1900.0,
                    "inputs": {"message_count": 7},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 700, "output": 110},
                    "error": None,
                    "children": [],
                },
                # Repeated search — third time (anti-pattern)
                {
                    "name": "tool_search_knowledge_base",
                    "span_type": "tool_call",
                    "start_time": 2007.0,
                    "end_time": 2007.02,
                    "duration_ms": 20.0,
                    "inputs": {"tool": "search_knowledge_base", "input": {"query": "caching"}},
                    "outputs": {"result": "[{'id': 'doc_008'}]"},
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "llm_call_5",
                    "span_type": "llm_call",
                    "start_time": 2007.1,
                    "end_time": 2009.0,
                    "duration_ms": 1900.0,
                    "inputs": {"message_count": 9},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 900, "output": 130},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_get_document",
                    "span_type": "tool_call",
                    "start_time": 2009.0,
                    "end_time": 2009.01,
                    "duration_ms": 10.0,
                    "inputs": {"tool": "get_document", "input": {"doc_id": "doc_008"}},
                    "outputs": {"result": "{'id': 'doc_008'}"},
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                # Slow LLM call (anti-pattern: >10s)
                {
                    "name": "llm_call_6",
                    "span_type": "llm_call",
                    "start_time": 2009.1,
                    "end_time": 2017.5,
                    "duration_ms": 8400.0,
                    "inputs": {"message_count": 11},
                    "outputs": {"stop_reason": "end_turn"},
                    "tokens": {"input": 1100, "output": 250},
                    "error": None,
                    "children": [],
                },
            ],
        }
    ],
}

SAMPLE_TRACE_ERROR = {
    "trace_id": "trace_error",
    "question": "What is GraphQL?",
    "spans": [
        {
            "name": "answer_question",
            "span_type": "agent_step",
            "start_time": 3000.0,
            "end_time": 3004.0,
            "duration_ms": 4000.0,
            "inputs": {"question": "What is GraphQL?"},
            "outputs": {},
            "tokens": {},
            "error": "No relevant documents found",
            "children": [
                {
                    "name": "llm_call_1",
                    "span_type": "llm_call",
                    "start_time": 3000.1,
                    "end_time": 3001.3,
                    "duration_ms": 1200.0,
                    "inputs": {"message_count": 1},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 150, "output": 70},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_search_knowledge_base",
                    "span_type": "tool_call",
                    "start_time": 3001.3,
                    "end_time": 3001.32,
                    "duration_ms": 20.0,
                    "inputs": {"tool": "search_knowledge_base", "input": {"query": "GraphQL"}},
                    "outputs": {"result": "[]"},
                    "tokens": {},
                    "error": "No results found",
                    "children": [],
                },
                {
                    "name": "llm_call_2",
                    "span_type": "llm_call",
                    "start_time": 3001.4,
                    "end_time": 3003.8,
                    "duration_ms": 2400.0,
                    "inputs": {"message_count": 3},
                    "outputs": {"stop_reason": "end_turn"},
                    "tokens": {"input": 300, "output": 180},
                    "error": None,
                    "children": [],
                },
            ],
        }
    ],
}

ALL_SAMPLE_TRACES = {
    "good": SAMPLE_TRACE_GOOD,
    "anti_patterns": SAMPLE_TRACE_ANTI_PATTERNS,
    "error": SAMPLE_TRACE_ERROR,
}


# ---------------------------------------------------------------------------
# Trace analysis
# ---------------------------------------------------------------------------


def _collect_all_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten a span tree into a list (depth-first)."""
    result: list[dict[str, Any]] = []
    for span in spans:
        result.append(span)
        result.extend(_collect_all_spans(span.get("children", [])))
    return result


class TraceAnalyzer:
    """Analyzes execution traces to detect patterns and compute metrics."""

    def load_trace(self, path: str) -> dict[str, Any]:
        """Load a trace from a JSON file."""
        from pathlib import Path

        with Path(path).open(encoding="utf-8") as f:
            result: dict[str, Any] = json.load(f)
            return result

    def load_trace_from_dict(self, trace_data: dict[str, Any]) -> dict[str, Any]:
        """Load a trace from an in-memory dictionary."""
        return trace_data

    def compute_metrics(self, trace: dict[str, Any]) -> dict[str, Any]:
        """Compute aggregate metrics: total tokens, cost, step count, latency breakdown."""
        all_spans = _collect_all_spans(trace.get("spans", []))

        total_input_tokens = 0
        total_output_tokens = 0
        llm_latency_ms = 0.0
        tool_latency_ms = 0.0
        llm_call_count = 0
        tool_call_count = 0
        error_count = 0

        for span in all_spans:
            tokens = span.get("tokens", {})
            total_input_tokens += tokens.get("input", 0)
            total_output_tokens += tokens.get("output", 0)

            duration = span.get("duration_ms", 0.0)
            span_type = span.get("span_type", "")

            if span_type == "llm_call":
                llm_latency_ms += duration
                llm_call_count += 1
            elif span_type == "tool_call":
                tool_latency_ms += duration
                tool_call_count += 1

            if span.get("error"):
                error_count += 1

        total_tokens = total_input_tokens + total_output_tokens
        estimated_cost = (
            total_input_tokens * COST_PER_INPUT_TOKEN + total_output_tokens * COST_PER_OUTPUT_TOKEN
        )

        # Total duration from root spans
        total_duration_ms = sum(s.get("duration_ms", 0.0) for s in trace.get("spans", []))

        return {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
            "llm_call_count": llm_call_count,
            "tool_call_count": tool_call_count,
            "error_count": error_count,
            "total_duration_ms": round(total_duration_ms, 2),
            "llm_latency_ms": round(llm_latency_ms, 2),
            "tool_latency_ms": round(tool_latency_ms, 2),
            "total_spans": len(all_spans),
        }

    def detect_anti_patterns(self, trace: dict[str, Any]) -> list[dict[str, str]]:
        """Detect anti-patterns like excessive tool calls, loops, failed tools."""
        issues: list[dict[str, str]] = []
        all_spans = _collect_all_spans(trace.get("spans", []))

        # Check 1: Excessive LLM calls (>5 for a single question)
        llm_calls = [s for s in all_spans if s.get("span_type") == "llm_call"]
        if len(llm_calls) > 5:
            issues.append(
                {
                    "pattern": "excessive_llm_calls",
                    "severity": "warning",
                    "message": f"Found {len(llm_calls)} LLM calls — consider simplifying the prompt",
                }
            )

        # Check 2: Repeated identical tool calls
        tool_calls = [s for s in all_spans if s.get("span_type") == "tool_call"]
        seen_calls: dict[str, int] = {}
        for tc in tool_calls:
            tool_input = tc.get("inputs", {}).get("input", {})
            key = f"{tc.get('inputs', {}).get('tool', '')}:{json.dumps(tool_input, sort_keys=True)}"
            seen_calls[key] = seen_calls.get(key, 0) + 1

        for key, count in seen_calls.items():
            if count > 1:
                issues.append(
                    {
                        "pattern": "repeated_tool_call",
                        "severity": "warning",
                        "message": f"Tool call '{key}' repeated {count} times — agent may be looping",
                    }
                )

        # Check 3: High token consumption (>2000 total for a simple task)
        total_tokens = sum(
            s.get("tokens", {}).get("input", 0) + s.get("tokens", {}).get("output", 0)
            for s in all_spans
        )
        if total_tokens > 2000:
            issues.append(
                {
                    "pattern": "high_token_usage",
                    "severity": "info",
                    "message": f"Total token usage is {total_tokens} — review if the task warrants it",
                }
            )

        # Check 4: Failed tool calls that weren't retried
        failed_tools = [s for s in tool_calls if s.get("error")]
        for ft in failed_tools:
            tool_name = ft.get("inputs", {}).get("tool", "unknown")
            retried = any(
                s.get("inputs", {}).get("tool") == tool_name
                for s in tool_calls
                if s is not ft and not s.get("error")
            )
            if not retried:
                issues.append(
                    {
                        "pattern": "unretried_failure",
                        "severity": "error",
                        "message": f"Tool '{tool_name}' failed but was not retried",
                    }
                )

        # Check 5: Very long spans (>10s for a single operation)
        for span in all_spans:
            duration = span.get("duration_ms", 0.0)
            if duration > 10000 and span.get("span_type") != "agent_step":
                issues.append(
                    {
                        "pattern": "slow_span",
                        "severity": "warning",
                        "message": (
                            f"Span '{span['name']}' took {duration:.0f}ms (>{10000}ms threshold)"
                        ),
                    }
                )

        return issues

    def compare_traces(self, trace_a: dict[str, Any], trace_b: dict[str, Any]) -> dict[str, Any]:
        """Compare two traces of the same task."""
        metrics_a = self.compute_metrics(trace_a)
        metrics_b = self.compute_metrics(trace_b)

        comparison: dict[str, Any] = {}
        for key in metrics_a:
            val_a = metrics_a[key]
            val_b = metrics_b[key]
            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                diff = val_b - val_a
                pct = (diff / val_a * 100) if val_a != 0 else 0.0
                comparison[key] = {
                    "trace_a": val_a,
                    "trace_b": val_b,
                    "diff": round(diff, 4),
                    "pct_change": round(pct, 1),
                }

        return comparison


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    """Analyze sample traces: compute metrics, detect anti-patterns, compare."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Trace Analysis[/bold cyan]\n\n"
            "Loads recorded traces and computes aggregate metrics, detects\n"
            "anti-patterns, and compares traces. Works entirely offline.\n\n"
            "Concepts: metrics aggregation, anti-pattern detection, trace comparison",
            title="02 - Trace Analysis",
        )
    )

    analyzer = TraceAnalyzer()

    # --- Metrics table ---
    console.print("\n[bold]Trace Metrics[/bold]\n")

    metrics_table = Table(title="Metrics by Trace")
    metrics_table.add_column("Metric", style="cyan")
    for name in ALL_SAMPLE_TRACES:
        metrics_table.add_column(name, justify="right")

    all_metrics: dict[str, dict[str, Any]] = {}
    for name, trace in ALL_SAMPLE_TRACES.items():
        all_metrics[name] = analyzer.compute_metrics(trace)

    metric_labels = {
        "total_tokens": "Total Tokens",
        "total_input_tokens": "Input Tokens",
        "total_output_tokens": "Output Tokens",
        "estimated_cost_usd": "Est. Cost (USD)",
        "llm_call_count": "LLM Calls",
        "tool_call_count": "Tool Calls",
        "error_count": "Errors",
        "total_duration_ms": "Total Duration (ms)",
        "llm_latency_ms": "LLM Latency (ms)",
        "tool_latency_ms": "Tool Latency (ms)",
        "total_spans": "Total Spans",
    }

    for key, label in metric_labels.items():
        row = [label]
        for name in ALL_SAMPLE_TRACES:
            val = all_metrics[name].get(key, 0)
            if key == "estimated_cost_usd":
                row.append(f"${val:.6f}")
            elif isinstance(val, float):
                row.append(f"{val:.1f}")
            else:
                row.append(str(val))
        metrics_table.add_row(*row)

    console.print(metrics_table)

    # --- Anti-pattern detection ---
    console.print("\n[bold]Anti-Pattern Detection[/bold]\n")

    for name, trace in ALL_SAMPLE_TRACES.items():
        issues = analyzer.detect_anti_patterns(trace)
        if issues:
            issue_table = Table(title=f"Issues in '{name}'")
            issue_table.add_column("Severity", style="bold")
            issue_table.add_column("Pattern")
            issue_table.add_column("Message")
            for issue in issues:
                severity = issue["severity"]
                style = {"error": "red", "warning": "yellow", "info": "blue"}.get(severity, "")
                issue_table.add_row(
                    f"[{style}]{severity.upper()}[/{style}]",
                    issue["pattern"],
                    issue["message"],
                )
            console.print(issue_table)
        else:
            console.print(f"  [green]No issues detected in '{name}'[/green]")
        console.print()

    # --- Trace comparison ---
    console.print("[bold]Trace Comparison: good vs anti_patterns[/bold]\n")

    comparison = analyzer.compare_traces(SAMPLE_TRACE_GOOD, SAMPLE_TRACE_ANTI_PATTERNS)
    comp_table = Table(title="Comparison")
    comp_table.add_column("Metric", style="cyan")
    comp_table.add_column("Good", justify="right")
    comp_table.add_column("Anti-Patterns", justify="right")
    comp_table.add_column("Diff", justify="right")
    comp_table.add_column("% Change", justify="right")

    for key, vals in comparison.items():
        label = metric_labels.get(key, key)
        pct = vals["pct_change"]
        pct_style = "red" if pct > 0 else "green" if pct < 0 else ""
        comp_table.add_row(
            label,
            str(vals["trace_a"]),
            str(vals["trace_b"]),
            str(vals["diff"]),
            f"[{pct_style}]{pct:+.1f}%[/{pct_style}]" if pct_style else f"{pct:+.1f}%",
        )

    console.print(comp_table)


if __name__ == "__main__":
    main()
