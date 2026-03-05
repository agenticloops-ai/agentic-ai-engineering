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

import json
import os
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import anthropic
from common import AnthropicTokenTracker, setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-5-20250929"

KNOWLEDGE_BASE = [
    {
        "id": "doc_001",
        "title": "Microservices Architecture",
        "content": (
            "Microservices architecture decomposes applications into small, "
            "independent services. Each service runs in its own process, "
            "communicates via APIs, and can be deployed independently. Benefits "
            "include scalability, fault isolation, and technology flexibility. "
            "Challenges include distributed system complexity, data consistency, "
            "and operational overhead."
        ),
        "tags": ["architecture", "microservices", "distributed-systems"],
    },
    {
        "id": "doc_002",
        "title": "REST API Design",
        "content": (
            "REST APIs follow resource-oriented design principles. Use nouns "
            "for endpoints, HTTP methods for actions, and status codes for "
            "results. Best practices include versioning, pagination for "
            "collections, and consistent error response formats."
        ),
        "tags": ["api", "rest", "design"],
    },
    {
        "id": "doc_003",
        "title": "Database Indexing",
        "content": (
            "Database indexes improve query performance by creating efficient "
            "lookup structures. B-tree indexes handle equality and range "
            "queries. Composite indexes support multi-column queries but column "
            "order matters. Over-indexing slows writes and wastes storage. Use "
            "EXPLAIN to analyze query plans."
        ),
        "tags": ["database", "performance", "indexing"],
    },
    {
        "id": "doc_004",
        "title": "Authentication and Authorization",
        "content": (
            "Authentication verifies identity, authorization controls access. "
            "JWT tokens enable stateless authentication. OAuth 2.0 provides "
            "delegated access. Always hash passwords with bcrypt or argon2. "
            "Implement rate limiting and account lockout."
        ),
        "tags": ["security", "authentication", "authorization"],
    },
    {
        "id": "doc_005",
        "title": "CI/CD Pipelines",
        "content": (
            "CI automatically builds and tests code on every commit. CD "
            "automatically deploys passing builds. Key practices: fast feedback "
            "loops, trunk-based development, feature flags, and automated "
            "rollback."
        ),
        "tags": ["devops", "ci-cd", "automation"],
    },
    {
        "id": "doc_006",
        "title": "Container Orchestration with Kubernetes",
        "content": (
            "Kubernetes manages containerized workloads. Core concepts: Pods, "
            "Services, Deployments, ConfigMaps/Secrets. Key features: "
            "auto-scaling, self-healing, rolling updates, service discovery."
        ),
        "tags": ["devops", "kubernetes", "containers"],
    },
    {
        "id": "doc_007",
        "title": "Event-Driven Architecture",
        "content": (
            "Event-driven architecture uses events to trigger communication "
            "between services. Patterns: event sourcing, CQRS, pub/sub. "
            "Benefits: loose coupling, scalability, audit trails. Challenges: "
            "eventual consistency, event ordering."
        ),
        "tags": ["architecture", "events", "messaging"],
    },
    {
        "id": "doc_008",
        "title": "Caching Strategies",
        "content": (
            "Caching reduces latency by storing frequently accessed data in "
            "memory. Strategies: cache-aside, write-through, write-behind. Use "
            "Redis or Memcached. Set appropriate TTLs and implement cache "
            "invalidation."
        ),
        "tags": ["performance", "caching", "redis"],
    },
]

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "Search the knowledge base for documents matching a query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Max results", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_document",
        "description": "Retrieve a specific document by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string", "description": "Document ID"}},
            "required": ["doc_id"],
        },
    },
]

SYSTEM_PROMPT = (
    "You are a research assistant. Use the search_knowledge_base and get_document tools "
    "to find information before answering. Always ground your answers in the documents found. "
    "If no relevant documents are found, say so."
)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def search_knowledge_base(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    """Search knowledge base by matching query terms against titles, content, and tags."""
    query_terms = query.lower().split()
    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in KNOWLEDGE_BASE:
        searchable = f"{doc['title']} {doc['content']} {' '.join(doc['tags'])}".lower()
        score = sum(1 for term in query_terms if term in searchable)
        if score > 0:
            scored.append((score, {"id": doc["id"], "title": doc["title"], "score": score}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:max_results]]


def get_document(doc_id: str) -> dict[str, Any]:
    """Retrieve a document by ID."""
    for doc in KNOWLEDGE_BASE:
        if doc["id"] == doc_id:
            return doc
    return {"error": f"Document not found: {doc_id}"}


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "search_knowledge_base": search_knowledge_base,
    "get_document": get_document,
}


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> Any:
    """Execute a tool and return its result."""
    if tool_name not in TOOL_FUNCTIONS:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return TOOL_FUNCTIONS[tool_name](**tool_input)
    except Exception as e:
        logger.error("Tool execution error: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tracing infrastructure
# ---------------------------------------------------------------------------


@dataclass
class Span:
    """A single traced operation."""

    name: str
    span_type: str  # "llm_call", "tool_call", "agent_step", "search"
    start_time: float
    end_time: float | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list["Span"] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        """Convert span to a serializable dictionary."""
        return {
            "name": self.name,
            "span_type": self.span_type,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 2),
            "inputs": self.inputs,
            "outputs": self.outputs,
            "metadata": self.metadata,
            "tokens": self.tokens,
            "error": self.error,
            "children": [child.to_dict() for child in self.children],
        }


class TraceCollector:
    """Collects execution traces with hierarchical spans."""

    def __init__(self) -> None:
        self.trace_id: str = str(uuid.uuid4())[:8]
        self.root_spans: list[Span] = []
        self._span_stack: list[Span] = []

    @contextmanager
    def span(
        self, name: str, span_type: str, inputs: dict[str, Any] | None = None
    ) -> Generator[Span, None, None]:
        """Context manager for creating traced spans."""
        span = Span(
            name=name,
            span_type=span_type,
            start_time=time.time(),
            inputs=inputs or {},
        )

        # Nest under current parent, or add as root
        if self._span_stack:
            self._span_stack[-1].children.append(span)
        else:
            self.root_spans.append(span)

        self._span_stack.append(span)
        try:
            yield span
        except Exception as e:
            span.error = str(e)
            raise
        finally:
            span.end_time = time.time()
            self._span_stack.pop()

    def traced(self, name: str, span_type: str) -> Callable:
        """Decorator for tracing function calls."""

        def decorator(func: Callable) -> Callable:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.span(name, span_type, inputs={"args": str(args), **kwargs}) as s:
                    result = func(*args, **kwargs)
                    s.outputs = {"result": str(result)[:200]}
                    return result

            return wrapper

        return decorator

    def to_dict(self) -> dict[str, Any]:
        """Export trace as a serializable dictionary."""
        return {
            "trace_id": self.trace_id,
            "spans": [span.to_dict() for span in self.root_spans],
        }

    def save(self, path: str) -> None:
        """Save trace to JSON file."""
        from pathlib import Path

        with Path(path).open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info("Trace saved to %s", path)


# ---------------------------------------------------------------------------
# Traced research assistant
# ---------------------------------------------------------------------------


class TracedResearchAssistant:
    """Research assistant with full execution tracing."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        knowledge_base: list[dict[str, Any]],
        tracer: TraceCollector,
    ) -> None:
        self.client = client
        self.knowledge_base = knowledge_base
        self.tracer = tracer
        self.token_tracker = AnthropicTokenTracker()

    def answer(self, question: str) -> dict[str, Any]:
        """Answer a question with full tracing."""
        with self.tracer.span("answer_question", "agent_step", {"question": question}) as root:
            messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
            llm_call_count = 0

            while True:
                llm_call_count += 1
                with self.tracer.span(
                    f"llm_call_{llm_call_count}",
                    "llm_call",
                    {"message_count": len(messages)},
                ) as llm_span:
                    response = self.client.messages.create(
                        model=MODEL,
                        max_tokens=1024,
                        system=SYSTEM_PROMPT,
                        tools=TOOLS,
                        messages=messages,
                    )
                    self.token_tracker.track(response.usage)
                    llm_span.tokens = {
                        "input": response.usage.input_tokens,
                        "output": response.usage.output_tokens,
                    }
                    llm_span.outputs = {"stop_reason": response.stop_reason}

                # Process response
                tool_uses = []
                text_parts: list[str] = []
                for block in response.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                    elif hasattr(block, "name") and hasattr(block, "input"):
                        tool_uses.append(block)

                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason != "tool_use" or not tool_uses:
                    answer_text = "\n".join(text_parts)
                    root.outputs = {"answer": answer_text[:200], "llm_calls": llm_call_count}
                    return {
                        "answer": answer_text,
                        "llm_calls": llm_call_count,
                        "trace": self.tracer.to_dict(),
                    }

                # Execute tools with tracing
                tool_results = []
                for tool_use in tool_uses:
                    with self.tracer.span(
                        f"tool_{tool_use.name}",
                        "tool_call",
                        {"tool": tool_use.name, "input": tool_use.input},
                    ) as tool_span:
                        result = execute_tool(tool_use.name, tool_use.input)
                        tool_span.outputs = {"result": str(result)[:200]}

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps(result, default=str),
                        }
                    )

                messages.append({"role": "user", "content": tool_results})

                if llm_call_count >= 10:
                    root.error = "Max iterations reached"
                    return {"answer": "Max iterations reached", "llm_calls": llm_call_count}


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
        assistant = TracedResearchAssistant(client, KNOWLEDGE_BASE, tracer)

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
