<!-- ---
title: "Sandboxing"
description: "Run agent-generated code and tool calls in isolation with resource limits and timeouts"
icon: "shield"
status: "coming-soon"
--- -->

# Sandboxing

Run agent-generated code and tool calls without handing over the machine. Start with a portable subprocess sandbox — stripped environment, resource limits, ephemeral working directory, and timeouts — then reach for real container isolation when you need a hard boundary.

## 🎯 What You'll Learn

- Contain execution with `subprocess`, `resource.setrlimit`, and a stripped environment
- Enforce CPU, memory, and wall-clock limits on agent-run code
- Add an optional Docker (`--network none`) tier for a real isolation boundary
- Understand what each tier actually protects against — and what it doesn't

> 🚧 **Coming soon** — [Subscribe to our Substack](https://agenticloopsai.substack.com) or ⭐️ star the repo to get notified when this tutorial drops.
