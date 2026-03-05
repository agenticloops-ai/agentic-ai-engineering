<!-- ---
title: "Evals"
description: "Build evaluation suites that measure accuracy, quality, and regression over time"
icon: "bar-chart"
--- -->

# Evals

Move beyond deterministic assertions to **statistical evaluation** of agent quality. Following Anthropic's eval-driven development methodology: define success criteria as eval tasks, score with multiple grader types, track quality over time, and catch regressions automatically.

## 🎯 What You'll Learn

- Build code-based graders: keyword matching, regex, source citation, tool-call verification
- Implement the **LLM-as-judge** pattern with structured rubrics and chain-of-thought judging
- Design **golden datasets** — curated input/output pairs for regression testing
- Build end-to-end eval pipelines with multi-grader scoring
- Detect regressions by comparing pass rates against baselines
- Understand Anthropic's eval vocabulary: task, trial, transcript, outcome, grader

## 📦 Available Examples

| Script | File | Description |
| ------ | ---- | ----------- |
| Code-Based Graders | [01_code_based_graders.py](01_code_based_graders.py) | Keyword, regex, citation, and tool-call graders |
| LLM-as-Judge | [02_llm_as_judge.py](02_llm_as_judge.py) | Structured rubric scoring with chain-of-thought |
| Eval Pipeline | [03_eval_pipeline.py](03_eval_pipeline.py) | End-to-end: dataset → trials → grading → regression detection |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 04-testing-evaluation/02-evals python 01_code_based_graders.py

# Example
uv run --directory 04-testing-evaluation/02-evals python 03_eval_pipeline.py
```

All scripts work in **simulated mode** without API keys (using pre-defined responses) and in **live mode** with an `ANTHROPIC_API_KEY`.

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### 1. Eval Vocabulary (from Anthropic)

| Term | Definition |
|------|-----------|
| **Task** | A test case with inputs and success criteria |
| **Trial** | One stochastic run of a task (run multiple to capture variance) |
| **Transcript** | Complete record of the agent's actions |
| **Outcome** | Final environment state after the agent finishes |
| **Grader** | Logic that scores some aspect of agent performance |
| **pass@k** | Probability of at least one success in k trials |
| **pass^k** | All k trials must succeed (tests consistency) |

### 2. Three Grader Types

```python
# Code-based: fast, deterministic, cheap
class KeywordGrader:
    def grade(self, answer, expected_keywords) -> GraderResult: ...

# Model-based: flexible, nuanced, expensive
class LLMJudge:
    def evaluate(self, question, answer, reference) -> JudgeResult: ...

# Human: gold standard, very expensive, not scalable
# (Referenced but not implemented — use for calibrating automated graders)
```

### 3. LLM-as-Judge with Structured Output

Force structured scoring using tool_choice:

```python
JUDGE_TOOLS = [{
    "name": "submit_evaluation",
    "input_schema": {
        "properties": {
            "reasoning": {"type": "string"},       # Chain-of-thought first
            "accuracy_score": {"type": "integer"},  # Then score
            "completeness_score": {"type": "integer"},
            "grounding_score": {"type": "integer"},
        }
    }
}]
# Use tool_choice={"type": "tool", "name": "submit_evaluation"}
```

### 4. Golden Dataset Design

Start with 15-20 curated tasks (Anthropic recommends starting with 20-50):

```json
{
    "id": "task_001",
    "question": "What are the key benefits of microservices?",
    "expected_keywords": ["scalability", "fault isolation"],
    "expected_source_ids": ["doc_001"],
    "difficulty": "easy",
    "category": "architecture"
}
```

Include a mix of: easy single-document tasks, hard cross-document synthesis, and out-of-scope questions that should be refused.

## ⚠️ Important Considerations

- **Start small** — 15-20 well-curated tasks beat 1000 generic ones
- **Calibrate your graders** — compare automated scores against human judgment
- **LLM-as-judge is not free** — each evaluation costs tokens; use code-based graders first
- **Track pass rates over time** — a 5% drop signals a regression worth investigating

## 🔗 Resources

- [Demystifying Evals for AI Agents — Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — Core eval vocabulary (task, trial, grader), grader taxonomy, and 8-step eval roadmap used throughout this tutorial
- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena — Zheng et al., 2023](https://arxiv.org/abs/2306.05685) — Systematic study of LLM judges: agreement rates with humans, position bias, and the structured rubric approach
- [Holistic Evaluation of Language Models (HELM) — Liang et al., 2022](https://arxiv.org/abs/2211.09110) — Multi-metric evaluation framework covering accuracy, calibration, robustness, fairness, and efficiency
- [OpenAI Evaluation Best Practices](https://platform.openai.com/docs/guides/evaluation-best-practices) — Practical guidance on eval design, golden datasets, and grading strategies
- [Eval-Driven Development](https://evaldriven.org/) — The discipline of building evals before features

## 👉 Next Steps

Once you've mastered evals, continue to:
- **[Tracing & Debugging](../03-tracing-debugging/)** — When an eval fails, traces show exactly *why*
- **Experiment** — Add tasks to the golden dataset from your own agent failures
- **Explore** — Try different rubric designs and compare judge consistency
