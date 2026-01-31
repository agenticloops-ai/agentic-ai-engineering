---
title: "Effective Agents Patterns"
description: "Architectural patterns that separate toy demos from real agents — learn when to chain, route, parallelize, or delegate"
---

# Effective Agents Patterns

Architectural patterns that separate toy demos from real agents. Based on Anthropic's [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — learn when to chain, route, parallelize, or delegate.

> 🚧 **Coming soon** — this module is under active development. [Subscribe to our Substack](https://agenticloopsai.substack.com) or ⭐️ star the repo to get notified when tutorials drop.

## 🗺️ Progression Path

```
Augmented LLM
    ↓
  (adds sequential steps)
    ↓
Prompt Chaining
    ↓
  (adds input classification)
    ↓
Routing
    ↓
  (adds concurrent execution)
    ↓
Parallelization
    ↓
  (adds dynamic decomposition)
    ↓
Orchestrator-Workers
    ↓
  (adds self-critique)
    ↓
Evaluator-Optimizer
    ↓
  (adds human oversight)
    ↓
Human in the Loop
```

## 📚 Tutorials

### [01 - Augmented LLM](01-augmented-llm/)

Give your LLM access to external knowledge through retrieval-augmented generation. Ground responses in real data instead of relying on training knowledge alone.

---

### [02 - Prompt Chaining](02-prompt-chaining/)

Break complex tasks into sequential steps where each LLM call builds on the previous output. Simple, debuggable, and surprisingly powerful.

---

### [03 - Routing](03-routing/)

Classify incoming requests and dispatch them to specialized handlers. One agent decides, others execute — the foundation of scalable systems.

---

### [04 - Parallelization](04-parallelization/)

Fan-out work across multiple LLM calls simultaneously, then aggregate results. Trade latency for throughput when tasks are independent.

---

### [05 - Orchestrator-Workers](05-orchestrator-workers/)

A central agent dynamically breaks down tasks and delegates to specialized workers. The pattern behind most "AI agent" products you see today.

---

### [06 - Evaluator-Optimizer](06-evaluator-optimizer/)

One LLM generates, another critiques, and the cycle repeats until quality thresholds are met. Self-improving output without human intervention.

---

### [07 - Human in the Loop](07-human-in-the-loop/)

Build approval gates, escalation paths, and feedback mechanisms. Every production agent needs a strategy for when to ask a human.

---

## 🔗 Resources

- [Building Effective Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents)
- [OpenAI Agent Patterns](https://platform.openai.com/docs/guides/agents)
- [Agentic Design Patterns — Andrew Ng](https://www.deeplearning.ai/the-batch/how-agents-can-improve-llm-performance/)
