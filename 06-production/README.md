---
title: "Production"
description: "The gap between 'works on my laptop' and 'runs reliably at scale' — principles, deployment, monitoring, cost control, and security"
---

# Production

The gap between "works on my laptop" and "runs reliably at scale." Principles, deployment, monitoring, cost control, and security for agents serving real users.

> 🚧 **Coming soon** — this module is under active development. [Subscribe to our Substack](https://agenticloopsai.substack.com) or ⭐️ star the repo to get notified when tutorials drop.

## 💡 Why This Module Matters

Most agent tutorials stop at the demo. This module covers what happens after — when your agent needs to handle real traffic, stay within budget, and not become a security liability.

## 📚 Tutorials

### [01 - 12-Factor Agents](01-twelve-factor-agents/)

Principles for building production-grade agents. Inspired by the 12-factor app methodology, adapted for the unique challenges of LLM-powered systems.

---

### [02 - Deployment Strategies](02-deployment-strategies/)

Containers, serverless, and scaling patterns. How to package and ship agents that handle variable load and long-running tasks.

---

### [03 - Monitoring & Observability](03-monitoring-observability/)

Metrics, structured logging, and distributed tracing for production agents. Know when things break before your users tell you.

---

### [04 - Cost Optimization](04-cost-optimization/)

Token budgets, caching strategies, model routing, and knowing when a smaller model is the right call. Keep costs predictable as usage grows.

---

### [05 - Security & Guardrails](05-security-guardrails/)

Authentication, sandboxing, prompt injection defense, and tool-use permissions. Build agents that are safe to expose to untrusted input.

---

### [06 - Error Handling & Resilience](06-error-handling-resilience/)

Retries, fallback models, graceful degradation, and rate limit handling. LLM APIs fail more than traditional APIs — build agents that recover automatically.

---

## 🔗 Resources

- [12-Factor Agents](https://github.com/humanlayer/12-factor-agents)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [Anthropic Safety Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/safety)
