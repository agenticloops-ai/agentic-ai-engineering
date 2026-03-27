<!-- ---
title: "Eval Harness"
description: "Capstone: complete evaluation pipeline combining all testing techniques"
icon: "award"
--- -->

# Eval Harness

The capstone project that **combines all five techniques** from this module into a single, reusable evaluation harness. Unit testing patterns, evals, tracing, red teaming, and benchmarking compose into a complete quality system for a real agent.

## 🎯 What You'll Learn

- Wire all 5 testing techniques into a unified evaluation pipeline
- Use Pydantic data models for type-safe eval infrastructure
- Build a modular `eval_harness` package with clear separation of concerns
- Generate comprehensive reports combining quality, safety, and benchmark metrics
- Practice **eval-driven development** end-to-end

## 📦 Available Examples

| Script | File | Description |
| ------ | ---- | ----------- |
| Eval Harness | [01_eval_harness.py](01_eval_harness.py) | Run the full evaluation pipeline |

### Package Modules

| Module | File | Description |
| ------ | ---- | ----------- |
| Models | [eval_harness/models.py](eval_harness/models.py) | Pydantic models: EvalTask, EvalTrial, EvalResult, etc. |
| Agent | [eval_harness/agent.py](eval_harness/agent.py) | Research assistant (live + simulated) |
| Graders | [eval_harness/graders.py](eval_harness/graders.py) | Keyword, citation, and composite graders |
| Tracer | [eval_harness/tracer.py](eval_harness/tracer.py) | Lightweight span-based trace collector |
| Red Team | [eval_harness/red_team.py](eval_harness/red_team.py) | Safety testing with adversarial inputs |
| Benchmark | [eval_harness/benchmark.py](eval_harness/benchmark.py) | Model comparison with Pareto analysis |
| Reporter | [eval_harness/reporter.py](eval_harness/reporter.py) | Rich terminal report generation |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 04-testing-evaluation/07-eval-harness python 01_eval_harness.py
```

The harness runs in **simulated mode** without API keys (using `SimulatedResearchAgent`) and in **live mode** with an `ANTHROPIC_API_KEY`.

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🏗️ Architecture

```
Load Tasks → Run Agent (with tracing) → Score (multi-grader) → Safety Test → Benchmark → Report
```

Each stage maps to a previous tutorial:

| Pipeline Stage | Module | From Tutorial |
|---------------|--------|---------------|
| Testable agent design | `agent.py` | [01 - Unit Testing](../01-unit-testing-agents/) |
| Golden dataset + grading | `graders.py` | [02 - Evals](../02-evals/) |
| Execution tracing | `tracer.py` | [03 - Tracing](../03-tracing-debugging/) |
| Adversarial testing | `red_team.py` | [04 - Red Teaming](../04-red-teaming-safety/) |
| Model comparison | `benchmark.py` | [05 - Benchmarking](../05-benchmarking/) |
| Unified reporting | `reporter.py` | New in capstone |

## 🔑 Key Concepts

### 1. Pydantic Data Models

Type-safe eval infrastructure with validation:

```python
class EvalTask(BaseModel):
    id: str
    question: str
    expected_keywords: list[str]
    difficulty: str = "medium"

class EvalResult(BaseModel):
    task_id: str
    trials: list[EvalTrial]
    grader_scores: list[GraderScore]
    pass_rate: float
```

### 2. Composite Grading

Multiple grader types per task, weighted scoring:

```python
class CompositeGrader:
    """Combines keyword + citation graders with configurable weights."""

    def grade(self, trial, task) -> list[GraderScore]:
        keyword_score = self.keyword_grader.grade(trial.answer, task.expected_keywords)
        citation_score = self.citation_grader.grade(trial.answer, task.expected_source_ids)
        # Weighted combination for overall pass/fail
```

### 3. The Eval Report

The harness generates a unified report:

```
╭─────────── Eval Report: Research Assistant ───────────╮
│                                                       │
│  📊 Quality Evals        12/15 tasks passed (80.0%)   │
│  🔒 Safety Score         7/8 attacks blocked (87.5%)  │
│  ⏱️  Avg Latency          1.5s per task               │
│  💰 Total Cost           $0.045                       │
│                                                       │
╰───────────────────────────────────────────────────────╯
```

## ⚠️ Important Considerations

- **Evals are living infrastructure** — maintain your golden dataset like production code
- **Safety is a first-class dimension** — red team results sit alongside accuracy results
- **Cost tracking is essential** — know what your eval suite costs before running it in CI/CD
- **Regression alerts need baselines** — store results from a known-good run as your comparison point

## 🔗 Resources

- [Demystifying Evals for AI Agents — Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — The eval methodology this harness implements: task → trial → grading → regression detection
- [EleutherAI Language Model Evaluation Harness](https://github.com/EleutherAI/lm-evaluation-harness) — Open-source eval framework for LLMs; the design inspiration for modular harness architecture
- [Eval-Driven Development](https://evaldriven.org/) — The discipline of defining success criteria as evals before building features
- [Building Effective Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents) — Agent design patterns that make agents testable through dependency injection and clear interfaces

## 👉 Next Steps

This is the capstone — you've completed the Testing & Evaluation module! From here:
- **Apply** — Build an eval harness for your own agents
- **Extend** — Add LLM-as-judge grading from [Tutorial 02](../02-evals/) to the composite grader
- **Integrate** — Run the harness in CI/CD to catch regressions automatically
- **Frameworks** — Plug in [eval frameworks](../06-eval-frameworks/) (Promptfoo, Braintrust, Langfuse) for production use
- **Explore** — Check out [Module 02: Effective Agents](../../02-effective-agents/) for more complex agents to test
