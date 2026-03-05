<!-- ---
title: "Tracing & Debugging"
description: "Trace every LLM call, tool invocation, and decision point"
icon: "search"
--- -->

# Tracing & Debugging

When an agent does something unexpected, you need to know **exactly why**. Tracing captures the full execution flow — every LLM call, tool invocation, decision point, and intermediate result — so you can reconstruct the agent's reasoning path post-hoc.

This tutorial teaches **observability as a first-class concern** using pure Python. No external dependencies — you learn the concepts, then apply them with production tools.

## 🎯 What You'll Learn

- Build a span-based trace collector with context managers and decorators
- Visualize execution traces as Rich tree hierarchies
- Detect anti-patterns: excessive calls, loops, repeated searches, high token usage
- Compare traces across runs of the same task
- Debug agent failures by walking recorded traces
- Replay agent execution from checkpoints

## 📦 Available Examples

| Script | File | Description |
| ------ | ---- | ----------- |
| Trace Collector | [01_trace_collector.py](01_trace_collector.py) | Build a `TraceCollector` with spans, context managers, decorators |
| Trace Analysis | [02_trace_analysis.py](02_trace_analysis.py) | Load traces, detect anti-patterns, compute metrics |
| Trace Debugging | [03_trace_debugging.py](03_trace_debugging.py) | Failure point identification, decision paths, replay |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 05-testing-evaluation/03-tracing-debugging python 01_trace_collector.py

# Example
uv run --directory 05-testing-evaluation/03-tracing-debugging python 02_trace_analysis.py
```

All scripts include **sample trace data** and work without API keys. Live mode activates automatically when `ANTHROPIC_API_KEY` is set.

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### 1. Span-Based Tracing

Every operation is a **span** with timing, inputs, outputs, and child spans:

```python
@dataclass
class Span:
    name: str           # "llm_call_1", "search_knowledge_base"
    span_type: str      # "llm_call", "tool_call", "agent_step"
    start_time: float
    end_time: float
    tokens: dict        # {"input": 150, "output": 80}
    children: list      # Nested child spans
    error: str | None   # Error message if span failed
```

### 2. Context Manager Tracing

The `TraceCollector` uses context managers for automatic span lifecycle:

```python
tracer = TraceCollector()

with tracer.span("answer_question", "agent_step") as root:
    with tracer.span("llm_call", "llm_call") as llm_span:
        response = client.messages.create(...)
        llm_span.tokens = {"input": 150, "output": 80}

    with tracer.span("search", "tool_call") as tool_span:
        results = search_knowledge_base(query)
```

### 3. Anti-Pattern Detection

Automated analysis catches common agent problems:

| Anti-Pattern | Symptom | Typical Cause |
|-------------|---------|---------------|
| Excessive LLM calls | >5 calls for a simple question | Missing stop conditions |
| Repeated searches | Same query searched twice | No result caching |
| High token usage | >2000 tokens for simple task | Verbose prompts or loops |
| Failed tool calls | Tool errors not retried | Missing error handling |
| Very long spans | >10s for a single operation | API timeouts or loops |

### 4. Trace-Based Debugging

When an eval fails, the trace shows the failure path:

```
1. Walk backward from the failed outcome
2. Find the first span with an error or unexpected output
3. Examine the inputs that led to the bad decision
4. Use TraceReplay to re-execute from that checkpoint
```

## ⚠️ Important Considerations

- **Pure Python, not production** — this tutorial teaches concepts. For production, use [Langfuse](https://langfuse.com/), [Datadog](https://www.datadoghq.com/), or [OpenTelemetry](https://opentelemetry.io/)
- **Trace storage grows fast** — in production, sample traces and set retention policies
- **Cost attribution matters** — knowing which step costs the most guides optimization

## 🔗 Resources

- [OpenTelemetry Documentation](https://opentelemetry.io/docs/) — Industry-standard specification for spans, traces, and context propagation used in production observability
- [Langfuse — Open Source LLM Observability](https://langfuse.com/) — Production tracing for LLM applications with cost tracking, scoring, and prompt management
- [Dapper, a Large-Scale Distributed Systems Tracing Infrastructure — Sigelman et al., 2010](https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/) — Google's seminal paper on span-based distributed tracing that inspired OpenTelemetry
- [The Three Pillars of Observability — Charity Majors](https://www.oreilly.com/library/view/distributed-systems-observability/9781492033431/ch04.html) — Metrics, logs, and traces as complementary observability signals

## 👉 Next Steps

Once you've mastered tracing, continue to:
- **[Red Teaming & Safety](../04-red-teaming-safety/)** — Test your agents against adversarial attacks
- **Experiment** — Instrument your own agents with the `TraceCollector`
- **Explore** — Connect traces to eval failures from [Tutorial 02](../02-evals/)
