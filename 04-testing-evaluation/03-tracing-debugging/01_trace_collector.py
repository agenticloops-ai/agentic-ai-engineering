"""
Trace Collector

Demonstrates how to build a pure Python tracing system for agent execution. Instruments
every LLM call, tool call, and agent step with hierarchical spans that capture timing,
token usage, inputs, and outputs — the foundation of agent observability.

Key concepts:
- Span-based tracing: nest operations in a tree to see the full execution picture
- Context-manager spans: automatic start/end timing with proper nesting
- Decorator-based tracing: instrument functions without modifying their bodies
- Trace serialization: export traces as JSON for later analysis and debugging
"""

import os
from typing import Any

import anthropic
from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

from shared.agent import TracedResearchAssistant
from shared.tracer import TraceCollector

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Visualization helpers
# ---------------------------------------------------------------------------


def build_span_tree(span_data: dict[str, Any], tree: Tree) -> None:
    """Recursively build a Rich tree from span data."""
    duration = span_data.get("duration_ms", 0)
    tokens = span_data.get("tokens", {})
    error = span_data.get("error")

    label = f"[bold]{span_data['name']}[/bold] [{span_data['span_type']}]"
    label += f"  {duration:.1f}ms"
    if tokens:
        label += f"  tokens: {tokens.get('input', 0)}in/{tokens.get('output', 0)}out"
    if error:
        label += f"  [red]ERROR: {error}[/red]"

    branch = tree.add(label)
    for child in span_data.get("children", []):
        build_span_tree(child, branch)


# ---------------------------------------------------------------------------
# Sample trace for offline mode
# ---------------------------------------------------------------------------

SAMPLE_TRACE = {
    "trace_id": "sample_001",
    "question": "What are the benefits of microservices?",
    "spans": [
        {
            "name": "answer_question",
            "span_type": "agent_step",
            "start_time": 1000.0,
            "end_time": 1003.5,
            "duration_ms": 3500.0,
            "inputs": {
                "question": "What are the benefits of microservices?",
            },
            "outputs": {
                "answer": "Microservices offer scalability...",
                "llm_calls": 3,
            },
            "metadata": {},
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
                    "metadata": {},
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
                    "outputs": {
                        "result": "[{'id': 'doc_001', 'title': 'Microservices'}]",
                    },
                    "metadata": {},
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
                    "metadata": {},
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
                    "inputs": {
                        "tool": "get_document",
                        "input": {"doc_id": "doc_001"},
                    },
                    "outputs": {
                        "result": "{'id': 'doc_001', 'title': 'Microservices'}",
                    },
                    "metadata": {},
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
                    "metadata": {},
                    "tokens": {"input": 450, "output": 120},
                    "error": None,
                    "children": [],
                },
            ],
        }
    ],
}


def main() -> None:
    """Run traced research assistant and visualize execution traces."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Trace Collector[/bold cyan]\n\n"
            "Instruments agent execution with hierarchical spans that capture\n"
            "timing, token usage, inputs, and outputs for every operation.\n\n"
            "Concepts: span hierarchy, context-manager tracing, trace serialization",
            title="01 - Trace Collector",
        )
    )

    # Determine run mode
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if has_api_key:
        console.print("\n[green]API key found — running live traced agent[/green]\n")
        client = anthropic.Anthropic()
        tracer = TraceCollector()
        assistant = TracedResearchAssistant(client, tracer)

        questions = [
            "What are the benefits of microservices?",
            "How should I design a REST API?",
        ]

        for question in questions:
            console.print(f"\n[bold yellow]Question:[/bold yellow] {question}")
            try:
                result = assistant.answer(question)
                console.print(f"[dim]Answer: {result['answer'][:150]}...[/dim]")
                console.print(f"[dim]LLM calls: {result['llm_calls']}[/dim]")
            except Exception as e:
                logger.error("Error answering question: %s", e)

        trace_data = tracer.to_dict()
        trace_path = "trace_output.json"
        tracer.save(trace_path)
        console.print(f"\n[green]Trace saved to {trace_path}[/green]")

    else:
        console.print("\n[yellow]No API key — using sample trace data[/yellow]\n")
        trace_data = SAMPLE_TRACE

    # Visualize the trace as a tree
    console.print("\n[bold]Trace Visualization[/bold]\n")

    tree = Tree(f"[bold magenta]Trace {trace_data.get('trace_id', 'unknown')}[/bold magenta]")
    for span_data in trace_data.get("spans", []):
        build_span_tree(span_data, tree)

    console.print(tree)

    # Summary statistics
    total_tokens = {"input": 0, "output": 0}
    span_count = 0

    def count_spans(spans: list[dict[str, Any]]) -> None:
        nonlocal span_count
        for s in spans:
            span_count += 1
            tokens = s.get("tokens", {})
            total_tokens["input"] += tokens.get("input", 0)
            total_tokens["output"] += tokens.get("output", 0)
            count_spans(s.get("children", []))

    count_spans(trace_data.get("spans", []))

    console.print(
        f"\n[bold]Summary:[/bold] {span_count} spans, "
        f"{total_tokens['input']} input tokens, "
        f"{total_tokens['output']} output tokens"
    )


if __name__ == "__main__":
    main()
