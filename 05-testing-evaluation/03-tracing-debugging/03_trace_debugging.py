"""
Trace Debugging

Demonstrates a trace-based debugging workflow: given a failing agent execution,
walk the recorded trace to find the failure point, extract the decision path,
suggest fixes, and replay from a checkpoint.

Key concepts:
- Failure-point detection: walk the span tree to find the first error or unexpected output
- Decision-path extraction: reconstruct the sequence of choices the agent made
- Fix suggestions: map failure types to actionable remediation steps
- Trace replay: list checkpoints and simulate re-execution from a chosen point
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
from rich.tree import Tree

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-5-20250929"


# ---------------------------------------------------------------------------
# Sample failing traces
# ---------------------------------------------------------------------------

# Failure 1: Agent searched wrong terms, found no results
TRACE_WRONG_SEARCH = {
    "trace_id": "fail_wrong_search",
    "question": "How does Kubernetes handle auto-scaling?",
    "expected_answer_contains": "auto-scaling",
    "spans": [
        {
            "name": "answer_question",
            "span_type": "agent_step",
            "start_time": 1000.0,
            "end_time": 1005.0,
            "duration_ms": 5000.0,
            "inputs": {"question": "How does Kubernetes handle auto-scaling?"},
            "outputs": {"answer": "I could not find relevant information."},
            "tokens": {},
            "error": None,
            "children": [
                {
                    "name": "llm_call_1",
                    "span_type": "llm_call",
                    "start_time": 1000.1,
                    "end_time": 1001.5,
                    "duration_ms": 1400.0,
                    "inputs": {"message_count": 1},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 160, "output": 70},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_search_knowledge_base",
                    "span_type": "tool_call",
                    "start_time": 1001.5,
                    "end_time": 1001.52,
                    "duration_ms": 20.0,
                    "inputs": {
                        "tool": "search_knowledge_base",
                        "input": {"query": "horizontal pod autoscaler HPA"},
                    },
                    "outputs": {"result": "[]"},
                    "tokens": {},
                    "error": "No results found for overly specific query",
                    "children": [],
                },
                {
                    "name": "llm_call_2",
                    "span_type": "llm_call",
                    "start_time": 1001.6,
                    "end_time": 1003.0,
                    "duration_ms": 1400.0,
                    "inputs": {"message_count": 3},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 280, "output": 65},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_search_knowledge_base",
                    "span_type": "tool_call",
                    "start_time": 3001.0,
                    "end_time": 3001.02,
                    "duration_ms": 20.0,
                    "inputs": {
                        "tool": "search_knowledge_base",
                        "input": {"query": "HPA metrics CPU"},
                    },
                    "outputs": {"result": "[]"},
                    "tokens": {},
                    "error": "No results — query too specific for knowledge base",
                    "children": [],
                },
                {
                    "name": "llm_call_3",
                    "span_type": "llm_call",
                    "start_time": 3001.1,
                    "end_time": 3004.8,
                    "duration_ms": 3700.0,
                    "inputs": {"message_count": 5},
                    "outputs": {"stop_reason": "end_turn"},
                    "tokens": {"input": 380, "output": 100},
                    "error": None,
                    "children": [],
                },
            ],
        }
    ],
}

# Failure 2: Agent found results but hallucinated information not in the documents
TRACE_HALLUCINATION = {
    "trace_id": "fail_hallucination",
    "question": "What caching strategies are available?",
    "expected_answer_contains": "cache-aside",
    "spans": [
        {
            "name": "answer_question",
            "span_type": "agent_step",
            "start_time": 2000.0,
            "end_time": 2004.0,
            "duration_ms": 4000.0,
            "inputs": {"question": "What caching strategies are available?"},
            "outputs": {
                "answer": (
                    "The main caching strategies are cache-aside, write-through, write-behind, "
                    "and distributed caching with consistent hashing. You should also consider "
                    "CDN-level caching with Cloudflare for static assets."
                ),
            },
            "tokens": {},
            "error": "hallucination_detected",
            "children": [
                {
                    "name": "llm_call_1",
                    "span_type": "llm_call",
                    "start_time": 2000.1,
                    "end_time": 2001.3,
                    "duration_ms": 1200.0,
                    "inputs": {"message_count": 1},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 150, "output": 60},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_search_knowledge_base",
                    "span_type": "tool_call",
                    "start_time": 2001.3,
                    "end_time": 2001.32,
                    "duration_ms": 20.0,
                    "inputs": {
                        "tool": "search_knowledge_base",
                        "input": {"query": "caching strategies"},
                    },
                    "outputs": {"result": "[{'id': 'doc_008', 'title': 'Caching Strategies'}]"},
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "llm_call_2",
                    "span_type": "llm_call",
                    "start_time": 2001.4,
                    "end_time": 2002.8,
                    "duration_ms": 1400.0,
                    "inputs": {"message_count": 3},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 300, "output": 50},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "tool_get_document",
                    "span_type": "tool_call",
                    "start_time": 2002.8,
                    "end_time": 2002.81,
                    "duration_ms": 10.0,
                    "inputs": {"tool": "get_document", "input": {"doc_id": "doc_008"}},
                    "outputs": {
                        "result": (
                            "Caching reduces latency... Strategies: cache-aside, write-through, "
                            "write-behind. Use Redis or Memcached."
                        ),
                    },
                    "tokens": {},
                    "error": None,
                    "children": [],
                },
                {
                    "name": "llm_call_3",
                    "span_type": "llm_call",
                    "start_time": 2002.9,
                    "end_time": 2003.9,
                    "duration_ms": 1000.0,
                    "inputs": {"message_count": 5},
                    "outputs": {
                        "stop_reason": "end_turn",
                        "answer_includes_hallucination": True,
                        "hallucinated_claims": [
                            "distributed caching with consistent hashing",
                            "CDN-level caching with Cloudflare",
                        ],
                    },
                    "tokens": {"input": 500, "output": 150},
                    "error": "LLM added claims not present in retrieved documents",
                    "children": [],
                },
            ],
        }
    ],
}

# Failure 3: Agent got stuck in a loop making repeated calls
TRACE_LOOP = {
    "trace_id": "fail_loop",
    "question": "Compare microservices and event-driven architecture",
    "expected_answer_contains": "microservices",
    "spans": [
        {
            "name": "answer_question",
            "span_type": "agent_step",
            "start_time": 3000.0,
            "end_time": 3020.0,
            "duration_ms": 20000.0,
            "inputs": {"question": "Compare microservices and event-driven architecture"},
            "outputs": {"answer": "Max iterations reached"},
            "tokens": {},
            "error": "Max iterations reached",
            "children": [
                {
                    "name": f"llm_call_{i}",
                    "span_type": "llm_call",
                    "start_time": 3000.0 + i * 2,
                    "end_time": 3001.5 + i * 2,
                    "duration_ms": 1500.0,
                    "inputs": {"message_count": 1 + i * 2},
                    "outputs": {"stop_reason": "tool_use"},
                    "tokens": {"input": 200 + i * 100, "output": 60},
                    "error": None,
                    "children": [],
                }
                for i in range(8)
            ]
            + [
                {
                    "name": f"tool_search_knowledge_base_{i}",
                    "span_type": "tool_call",
                    "start_time": 3001.5 + i * 2,
                    "end_time": 3001.52 + i * 2,
                    "duration_ms": 20.0,
                    "inputs": {
                        "tool": "search_knowledge_base",
                        "input": {"query": "microservices" if i % 2 == 0 else "event-driven"},
                    },
                    "outputs": {
                        "result": ("[{'id': 'doc_001'}]" if i % 2 == 0 else "[{'id': 'doc_007'}]"),
                    },
                    "tokens": {},
                    "error": None,
                    "children": [],
                }
                for i in range(8)
            ],
        }
    ],
}

ALL_FAILING_TRACES = {
    "wrong_search": TRACE_WRONG_SEARCH,
    "hallucination": TRACE_HALLUCINATION,
    "loop": TRACE_LOOP,
}


# ---------------------------------------------------------------------------
# Debugging tools
# ---------------------------------------------------------------------------


def _collect_all_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten a span tree into a list (depth-first)."""
    result: list[dict[str, Any]] = []
    for span in spans:
        result.append(span)
        result.extend(_collect_all_spans(span.get("children", [])))
    return result


class TraceDebugger:
    """Debug agent failures using execution traces."""

    def find_failure_point(self, trace: dict[str, Any]) -> dict[str, Any] | None:
        """Walk the trace to find the first span with an error."""
        all_spans = _collect_all_spans(trace.get("spans", []))
        for span in all_spans:
            if span.get("error"):
                return {
                    "span_name": span["name"],
                    "span_type": span.get("span_type", "unknown"),
                    "error": span["error"],
                    "inputs": span.get("inputs", {}),
                    "outputs": span.get("outputs", {}),
                    "duration_ms": span.get("duration_ms", 0),
                }
        return None

    def get_decision_path(self, trace: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract the sequence of decisions the agent made."""
        all_spans = _collect_all_spans(trace.get("spans", []))
        decisions: list[dict[str, Any]] = []

        for span in all_spans:
            span_type = span.get("span_type", "")
            if span_type == "agent_step":
                continue  # Skip the root wrapper

            decision: dict[str, Any] = {
                "step": len(decisions) + 1,
                "name": span["name"],
                "type": span_type,
                "duration_ms": span.get("duration_ms", 0),
            }

            if span_type == "llm_call":
                decision["action"] = "LLM decision"
                decision["outcome"] = span.get("outputs", {}).get("stop_reason", "unknown")
            elif span_type == "tool_call":
                tool_name = span.get("inputs", {}).get("tool", "unknown")
                tool_input = span.get("inputs", {}).get("input", {})
                decision["action"] = f"Called {tool_name}"
                decision["detail"] = json.dumps(tool_input)
                decision["outcome"] = "error" if span.get("error") else "success"

            if span.get("error"):
                decision["error"] = span["error"]

            decisions.append(decision)

        return decisions

    def suggest_fixes(self, failure: dict[str, Any]) -> list[str]:
        """Suggest possible fixes based on the failure type."""
        suggestions: list[str] = []
        error = failure.get("error", "")
        span_type = failure.get("span_type", "")

        # Wrong search / no results
        if "no results" in error.lower() or "not found" in error.lower():
            suggestions.append("Broaden the search query — use fewer, more general terms")
            suggestions.append("Add fallback logic: retry with simpler keywords on empty results")
            suggestions.append("Expand the knowledge base to cover more topics")

        # Hallucination
        if "hallucin" in error.lower() or "not present" in error.lower():
            suggestions.append(
                "Add explicit grounding instruction: "
                "'Only use information from retrieved documents'"
            )
            suggestions.append(
                "Implement a post-generation check that verifies claims against source docs"
            )
            suggestions.append("Lower the temperature to reduce creative generation")

        # Loop / max iterations
        if "max iterations" in error.lower() or "loop" in error.lower():
            suggestions.append("Add a seen-queries set to prevent repeated identical searches")
            suggestions.append("Reduce max_iterations and add a summarize-what-you-have fallback")
            suggestions.append(
                "Improve the system prompt to instruct the agent to synthesize after 2-3 searches"
            )

        # Slow span
        if span_type == "llm_call" and failure.get("duration_ms", 0) > 10000:
            suggestions.append("Check if the prompt is too long — summarize earlier context")
            suggestions.append("Consider using a faster model for intermediate steps")

        # Tool execution error
        if span_type == "tool_call" and error:
            suggestions.append("Add retry logic with exponential backoff for transient errors")
            suggestions.append("Validate tool inputs before execution")

        # Generic
        if not suggestions:
            suggestions.append("Review the full decision path to understand the agent's reasoning")
            suggestions.append("Add more detailed logging around the failing span")

        return suggestions


class TraceReplay:
    """Replay agent execution from a checkpoint in a recorded trace."""

    def list_checkpoints(self, trace: dict[str, Any]) -> list[dict[str, Any]]:
        """List available checkpoints (decision points) in the trace."""
        all_spans = _collect_all_spans(trace.get("spans", []))
        checkpoints: list[dict[str, Any]] = []

        for i, span in enumerate(all_spans):
            if span.get("span_type") in ("llm_call", "tool_call"):
                checkpoints.append(
                    {
                        "index": len(checkpoints),
                        "span_index": i,
                        "name": span["name"],
                        "type": span.get("span_type"),
                        "inputs": span.get("inputs", {}),
                        "had_error": bool(span.get("error")),
                    }
                )

        return checkpoints

    def replay_from(
        self,
        trace: dict[str, Any],
        checkpoint_index: int,
        client: anthropic.Anthropic | None = None,
    ) -> dict[str, Any]:
        """Replay from a specific checkpoint, optionally with a live LLM."""
        checkpoints = self.list_checkpoints(trace)

        if checkpoint_index < 0 or checkpoint_index >= len(checkpoints):
            return {"error": f"Invalid checkpoint index: {checkpoint_index}"}

        checkpoint = checkpoints[checkpoint_index]
        preceding = checkpoints[:checkpoint_index]

        # Build context from preceding steps
        context: list[dict[str, Any]] = []
        for cp in preceding:
            context.append(
                {
                    "step": cp["name"],
                    "type": cp["type"],
                    "inputs": cp["inputs"],
                }
            )

        result: dict[str, Any] = {
            "checkpoint": checkpoint,
            "preceding_steps": len(preceding),
            "context_summary": context,
        }

        if client is not None:
            # Live replay: re-run the LLM call with the context up to the checkpoint
            logger.info("Live replay from checkpoint %d: %s", checkpoint_index, checkpoint["name"])
            question = trace.get("question", "")

            system_prompt = (
                "You are a research assistant. The previous agent execution failed. "
                "You are replaying from a checkpoint. Answer the original question using "
                "the context provided. Be concise and grounded in facts."
            )

            context_text = f"Original question: {question}\n\n"
            context_text += "Execution context before failure:\n"
            for step in context:
                context_text += f"- {step['step']}: {json.dumps(step['inputs'])}\n"
            context_text += f"\nFailed at: {checkpoint['name']}\n"
            context_text += "Please provide a corrected response."

            token_tracker = AnthropicTokenTracker()
            start = time.time()
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": context_text}],
            )
            elapsed = (time.time() - start) * 1000
            token_tracker.track(response.usage)

            answer = ""
            for block in response.content:
                if hasattr(block, "text"):
                    answer += block.text

            result["replayed_answer"] = answer
            result["replay_duration_ms"] = round(elapsed, 2)
            result["replay_tokens"] = {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            }
        else:
            result["replayed_answer"] = (
                f"[Dry run] Would re-execute from '{checkpoint['name']}' "
                f"with {len(preceding)} preceding steps as context"
            )

        return result


# ---------------------------------------------------------------------------
# Visualization helpers
# ---------------------------------------------------------------------------


def _build_decision_tree(decisions: list[dict[str, Any]], tree: Tree) -> None:
    """Add decision steps to a Rich tree."""
    for d in decisions:
        label = f"[bold]Step {d['step']}:[/bold] {d['name']}"
        if d.get("action"):
            label += f" — {d['action']}"
        if d.get("outcome"):
            style = "red" if d["outcome"] == "error" else "green"
            label += f" [{style}]({d['outcome']})[/{style}]"
        if d.get("error"):
            label += f"\n  [red]Error: {d['error']}[/red]"
        if d.get("detail"):
            label += f"\n  [dim]{d['detail']}[/dim]"
        tree.add(label)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    """Demonstrate the trace-based debugging workflow."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Trace Debugging[/bold cyan]\n\n"
            "Given a failing agent execution, walk the trace to find the failure point,\n"
            "extract the decision path, suggest fixes, and list replay checkpoints.\n\n"
            "Concepts: failure detection, decision paths, fix suggestions, trace replay",
            title="03 - Trace Debugging",
        )
    )

    debugger = TraceDebugger()
    replayer = TraceReplay()

    for trace_name, trace in ALL_FAILING_TRACES.items():
        console.print(f"\n{'=' * 80}")
        console.print(
            f"\n[bold magenta]Debugging trace: {trace_name}[/bold magenta]"
            f"\n[dim]Question: {trace.get('question', 'N/A')}[/dim]\n"
        )

        # Step 1: Find the failure point
        failure = debugger.find_failure_point(trace)
        if failure:
            console.print(
                Panel(
                    f"[bold red]Failure Point[/bold red]\n\n"
                    f"Span: {failure['span_name']} ({failure['span_type']})\n"
                    f"Error: {failure['error']}\n"
                    f"Duration: {failure['duration_ms']:.0f}ms",
                    title="Failure Detected",
                    border_style="red",
                )
            )
        else:
            console.print("[green]No explicit failure found in trace[/green]")

        # Step 2: Show the decision path
        decisions = debugger.get_decision_path(trace)
        decision_tree = Tree(f"[bold]Decision Path ({len(decisions)} steps)[/bold]")
        _build_decision_tree(decisions, decision_tree)
        console.print(decision_tree)

        # Step 3: Suggest fixes
        if failure:
            suggestions = debugger.suggest_fixes(failure)
            console.print("\n[bold yellow]Suggested Fixes:[/bold yellow]")
            for i, suggestion in enumerate(suggestions, 1):
                console.print(f"  {i}. {suggestion}")

        # Step 4: List replay checkpoints
        checkpoints = replayer.list_checkpoints(trace)
        if checkpoints:
            cp_table = Table(title="Replay Checkpoints")
            cp_table.add_column("Index", justify="center")
            cp_table.add_column("Name")
            cp_table.add_column("Type")
            cp_table.add_column("Had Error", justify="center")
            for cp in checkpoints:
                error_marker = "[red]Yes[/red]" if cp["had_error"] else "[green]No[/green]"
                cp_table.add_row(
                    str(cp["index"]),
                    cp["name"],
                    cp["type"],
                    error_marker,
                )
            console.print()
            console.print(cp_table)

        # Step 5: Dry-run replay from the first errored checkpoint
        errored_cps = [cp for cp in checkpoints if cp["had_error"]]
        if errored_cps:
            first_error_cp = errored_cps[0]["index"]
            console.print(f"\n[bold]Dry-run replay from checkpoint {first_error_cp}:[/bold]")

            has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
            client = anthropic.Anthropic() if has_api_key else None

            replay_result = replayer.replay_from(trace, first_error_cp, client=client)
            console.print(f"  [dim]{replay_result['replayed_answer']}[/dim]")

            if replay_result.get("replay_tokens"):
                tokens = replay_result["replay_tokens"]
                console.print(
                    f"  [dim]Replay tokens: {tokens['input']}in / {tokens['output']}out, "
                    f"duration: {replay_result.get('replay_duration_ms', 0):.0f}ms[/dim]"
                )

    console.print(f"\n{'=' * 80}")
    console.print("\n[bold green]Debugging workflow complete.[/bold green]")


if __name__ == "__main__":
    main()
