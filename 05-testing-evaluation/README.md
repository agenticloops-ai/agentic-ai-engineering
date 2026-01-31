---
title: "Testing & Evaluation"
description: "Agents are non-deterministic — testing them requires different thinking. Measure quality, catch regressions, and build confidence before shipping"
---

# Testing & Evaluation

Agents are non-deterministic — testing them requires different thinking. Learn to measure quality, catch regressions, and build confidence before shipping.

> 🚧 **Coming soon** — this module is under active development. [Subscribe to our Substack](https://agenticloopsai.substack.com) or ⭐️ star the repo to get notified when tutorials drop.

## 💡 Why This Module Matters

You can't `assert output == expected` when the output changes every run. Agent testing requires new mental models — statistical assertions, LLM-as-judge, behavioral contracts, and adversarial probing.

## 📚 Tutorials

### [01 - Unit Testing Agents](01-unit-testing-agents/)

Mock LLM responses, test tool execution deterministically, and verify agent behavior without burning API credits on every test run.

---

### [02 - Evals](02-evals/)

Build evaluation suites that measure accuracy, quality, and regression over time. LLM-as-judge, golden datasets, and automated scoring pipelines.

---

### [03 - Tracing & Debugging](03-tracing-debugging/)

Trace every LLM call, tool invocation, and decision point. When your agent does something unexpected, you need to know exactly why.

---

### [04 - Red Teaming & Safety](04-red-teaming-safety/)

Adversarial testing for agents. Prompt injection, jailbreaks, tool misuse, and building guardrails that hold up under attack.

---

## 🔗 Resources

- [Anthropic Evals Guide](https://docs.anthropic.com/en/docs/build-with-claude/develop-tests)
- [OpenAI Evals](https://github.com/openai/evals)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
