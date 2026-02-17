<!-- ---
title: "Orchestrator-Workers"
description: "A central LLM dynamically decomposes tasks and delegates to parallel workers"
icon: "network"
--- -->

# Orchestrator-Workers — The Deep Dive Researcher

A central LLM dynamically breaks down a task, delegates subtasks to worker LLMs, and synthesizes their results. The programmer defines worker capabilities, not specific tasks.

## 🎯 What You'll Learn

- Use an LLM as an orchestrator that dynamically plans task decomposition
- Define worker capabilities while letting the orchestrator decide specific tasks
- Parallelize worker execution for throughput
- Synthesize diverse research into a coherent final output

## 📦 Available Examples

| Provider | File | Description |
|----------|------|-------------|
| ![Anthropic](../../common/badges/anthropic.svg) | [01_orchestrator_workers.py](01_orchestrator_workers.py) | Deep dive researcher with dynamic subtopic planning |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 02-effective-agents/05-orchestrator-workers python {script_name}

# Example
uv run --directory 02-effective-agents/05-orchestrator-workers python 01_orchestrator_workers.py
```

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### Dynamic Decomposition

Unlike [04 - Parallelization](../04-parallelization/) (where you hardcode the fan-out), the orchestrator uses an LLM to decide *what* subtopics to research based on the input:

```python
tool_choice={"type": "tool", "name": "create_research_plan"}
```

"Compare Bun vs Node.js" might produce: Performance, NPM Compatibility, Debugging, Deployment, Community.

### Worker Pattern

Workers are generic researchers — the orchestrator gives them specific prompts. You define the worker's *capability* (research a topic in depth), not the specific task. This is the key difference from parallelization: the LLM decides the work breakdown.

### Synthesis

After all workers complete, a synthesizer combines their independent research into a coherent article with proper flow and cross-references. This is a separate LLM call with its own system prompt — not just concatenation.

## ⚠️ Important Considerations

- The orchestrator's plan quality determines the final output quality
- Workers are independent — they can't reference each other's findings
- More subtopics = more API calls = higher cost. Consider limiting to 3-5

## 👉 Next Steps

- [06 - Evaluator-Optimizer](../06-evaluator-optimizer/) — add a quality feedback loop
- Experiment: give workers different models (fast model for simple topics, powerful for complex)
