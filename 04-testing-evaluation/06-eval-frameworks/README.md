<!-- ---
title: "Eval Frameworks"
description: "Integrate external eval frameworks: Promptfoo, Braintrust AutoEvals, Langfuse"
icon: "puzzle-piece"
--- -->

# Eval Frameworks

Explore **production eval frameworks** recommended in Anthropic's [Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents). Each script demonstrates a different framework's approach to evaluating the same research assistant agent — from YAML-driven configs to pre-built scorers to tracing platforms.

## 🎯 What You'll Learn

- Define eval suites declaratively using **Promptfoo's YAML configuration**
- Use **Braintrust AutoEvals** pre-built scorers (string similarity, factuality, custom classifiers)
- Instrument agents with **Langfuse** tracing and programmatic scoring
- Compare framework tradeoffs: CLI vs SDK, local vs cloud, string vs LLM-based scoring

## 📦 Available Examples

| Provider | File | Description |
| -------- | ---- | ----------- |
| Promptfoo | [01_promptfoo.py](01_promptfoo.py) | YAML config + custom Python provider and assertions |
| Braintrust | [02_braintrust_autoevals.py](02_braintrust_autoevals.py) | Pre-built scorers: Levenshtein, Factuality, custom classifiers |
| Langfuse | [03_langfuse.py](03_langfuse.py) | Decorator-based tracing + multi-type scoring |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+ and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

Each script runs in **simulated mode** without external dependencies. To use the actual frameworks:

```bash
# Core (all scripts work without these)
uv run --directory 04-testing-evaluation/06-eval-frameworks python 01_promptfoo.py

# With framework dependencies
uv sync --extra promptfoo    # adds pyyaml for YAML generation
uv sync --extra braintrust   # adds autoevals scorers
uv sync --extra langfuse     # adds langfuse SDK
uv sync --extra all           # all frameworks
```

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### Framework Comparison

| Aspect | Promptfoo | Braintrust AutoEvals | Langfuse |
|--------|-----------|---------------------|----------|
| **Type** | CLI tool (Node.js) | Python SDK | Python SDK |
| **Config** | YAML-driven | Code-driven | Code-driven |
| **Local?** | Yes (fully) | String scorers: yes | Needs server (or self-host) |
| **API keys** | Only for LLM providers | `OPENAI_API_KEY` for LLM scorers | `LANGFUSE_*` keys |
| **Best for** | Declarative eval suites | Pre-built scoring | Tracing + scoring |

### 1. Promptfoo: Declarative YAML Evals

Define providers, prompts, test cases, and assertions in YAML:

```yaml
providers:
  - id: "file://provider_agent.py"    # Custom Python provider
tests:
  - vars:
      question: "What are microservices benefits?"
    assert:
      - type: python                   # Custom Python assertion
        value: "file://assertion_keywords.py"
      - type: contains                 # Built-in string check
        value: "doc_001"
      - type: llm-rubric              # LLM-as-judge
        value: "Response should cover scalability and fault isolation."
```

### 2. Braintrust AutoEvals: Pre-Built Scorers

Use battle-tested scorers without building from scratch:

```python
from autoevals import Factuality, Levenshtein

# Local scorer — no API key needed
lev = Levenshtein()
result = lev.eval(output="hello wrld", expected="hello world")

# LLM scorer — needs OPENAI_API_KEY
fact = Factuality()
result = fact.eval(input="question", output="answer", expected="reference")
```

### 3. Langfuse: Tracing + Scoring

Instrument code with decorators and add scores programmatically:

```python
from langfuse import observe, get_client

@observe()  # Auto-creates trace with nested spans
def my_agent(question: str) -> str:
    return search_and_answer(question)

# Score the trace
langfuse = get_client()
langfuse.create_score(
    trace_id=trace_id,
    name="correctness",
    value=0.95,
    data_type="NUMERIC",
)
```

## ⚠️ Important Considerations

- **Pick a framework and iterate** — the blog advises investing energy in high-quality test cases and graders rather than framework selection
- **Many teams combine tools** — Promptfoo for CI/CD assertions, Langfuse for production tracing, autoevals for quick scoring
- **All scripts work without external dependencies** — simulated mode demonstrates the patterns; install frameworks when ready to use them for real
- **LLM-based scorers add cost** — Factuality/ClosedQA scorers call OpenAI; budget accordingly for large eval suites

## 🔗 Resources

- [Promptfoo Python Provider Docs](https://www.promptfoo.dev/docs/providers/python/)
- [Braintrust AutoEvals GitHub](https://github.com/braintrustdata/autoevals)
- [Langfuse Python SDK](https://langfuse.com/docs/sdk/python/decorators)
- [Demystifying Evals — Eval Frameworks Appendix](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

## 👉 Next Steps

- **Apply** — Pick the framework that fits your workflow and define eval tasks for your own agent
- **Combine** — Use Promptfoo for CI assertions + Langfuse for production tracing
- **Capstone** — See the [Eval Harness](../07-eval-harness/) for a framework-independent eval pipeline combining all techniques
