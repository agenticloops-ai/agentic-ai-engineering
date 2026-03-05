<!-- ---
title: "Benchmarking"
description: "Systematic head-to-head comparison of models, prompts, and architectures"
icon: "bar-chart-2"
--- -->

# Benchmarking

When you need to decide between Claude Sonnet vs. GPT-4o-mini, or between two prompt strategies, benchmarking gives you **data instead of vibes**. Systematic head-to-head comparison across dimensions that matter: accuracy, latency, cost, and reliability.

## 🎯 What You'll Learn

- Compare models on accuracy, latency, token usage, and cost
- Evaluate prompt strategies: zero-shot, few-shot, chain-of-thought
- Build configuration matrices (model × prompt) and run controlled experiments
- Find **Pareto-optimal** configurations (best accuracy for a given cost budget)
- Make data-driven model selection decisions

## 📦 Available Examples

| Script | File | Description |
| ------ | ---- | ----------- |
| Model Comparison | [01_model_comparison.py](01_model_comparison.py) | Same tasks across Claude Sonnet, Haiku, GPT-4.1 mini |
| Prompt Comparison | [02_prompt_comparison.py](02_prompt_comparison.py) | Zero-shot vs. few-shot vs. chain-of-thought |
| Benchmark Suite | [03_benchmark_suite.py](03_benchmark_suite.py) | Full matrix, Pareto analysis, report generation |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 04-testing-evaluation/05-benchmarking python 01_model_comparison.py

# Example
uv run --directory 04-testing-evaluation/05-benchmarking python 03_benchmark_suite.py
```

All scripts include **simulated results** and work without API keys. Live mode activates when `ANTHROPIC_API_KEY` (and optionally `OPENAI_API_KEY`) is set.

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### 1. Controlled Experimentation

Change one variable, hold others constant:

| Benchmark Type | Variable | Constant |
|---------------|----------|----------|
| Model comparison | Model | Same tasks, same prompt, same graders |
| Prompt comparison | Prompt strategy | Same model, same tasks, same graders |
| Full matrix | Model × Prompt | Same tasks, same graders |

### 2. Multi-Dimensional Evaluation

Accuracy alone is not enough:

```python
@dataclass
class BenchmarkResult:
    keyword_score: float   # Quality: did the answer contain expected info?
    latency_ms: float      # Speed: how fast was the response?
    input_tokens: int      # Efficiency: how many tokens consumed?
    cost_usd: float        # Cost: what did this run cost?
    tool_calls: int        # Behavior: how many tool calls needed?
```

### 3. Pareto Optimality

A configuration is **Pareto-optimal** if no other configuration is better on ALL dimensions:

```
Accuracy ↑
    │   ★ Sonnet+CoT (best quality, highest cost)
    │
    │       ★ Sonnet+ZeroShot (good balance)
    │
    │           ★ Haiku+FewShot (cheapest good option)
    │
    └──────────────────────────── Cost →
```

The Pareto frontier helps answer: "What's the best I can get for $X per task?"

### 4. Prompt Strategy Impact

Different prompt strategies trade quality for cost:

| Strategy | Accuracy | Cost | Use When |
|----------|----------|------|----------|
| Zero-shot | Baseline | Lowest | Simple, well-defined tasks |
| Few-shot | +10-15% | Medium | Tasks with clear patterns |
| Chain-of-thought | +15-25% | Highest | Complex reasoning tasks |

## ⚠️ Important Considerations

- **Run multiple trials** — 1 trial is not a benchmark; run 3-5 minimum per configuration
- **Account for variance** — non-deterministic outputs mean results vary between runs
- **Cost adds up fast** — a full matrix benchmark can be expensive; start with simulated mode
- **Token pricing changes** — update `cost_per_input_token` and `cost_per_output_token` as providers update pricing

## 🔗 Resources

- [Chatbot Arena: An Open Platform for Evaluating LLMs by Human Preference — Chiang et al., 2024](https://arxiv.org/abs/2403.04132) — Elo-rated human preference benchmarking methodology and the open leaderboard approach
- [Holistic Evaluation of Language Models (HELM) — Liang et al., 2022](https://arxiv.org/abs/2211.09110) — Multi-dimensional evaluation across accuracy, robustness, fairness, and efficiency
- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models — Wei et al., 2022](https://arxiv.org/abs/2201.11903) — The foundational CoT prompting paper showing significant accuracy gains on reasoning tasks
- [Language Models are Few-Shot Learners — Brown et al., 2020](https://arxiv.org/abs/2005.14165) — GPT-3 paper establishing few-shot in-context learning as a prompting paradigm
- [AI Agent Benchmarks — Evidently AI](https://www.evidentlyai.com/blog/ai-agent-benchmarks) — Overview of the benchmark landscape for AI agents

## 👉 Next Steps

Once you've mastered benchmarking, continue to:
- **[Eval Harness](../06-eval-harness/)** — The capstone that combines all 5 techniques into a unified pipeline
- **Experiment** — Add your own models and prompt strategies to the benchmark
- **Explore** — Combine benchmark results with eval scores from [Tutorial 02](../02-evals/)
