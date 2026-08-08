<!-- ---
title: "Loop Engineering"
description: "Harness the agent loop — add skills, MCP, sandboxing, subagents, hooks, and compaction one control surface at a time"
--- -->

# Loop Engineering

You built the bare agent loop in [Foundations](../01-foundations/05-agent-loop/). This module takes that loop and progressively *harnesses* it — each tutorial adds one orthogonal control surface that turns a naive loop into a real, extensible agent.

> 🚧 **Coming soon** — this module is under active development. [Subscribe to our Substack](https://agenticloopsai.substack.com) or ⭐️ star the repo to get notified when tutorials drop.

## 💡 Why This Module Exists

A raw loop calls the model, runs tools, and repeats. That's enough to demo — not to ship. Real agents inject capabilities on demand, run untrusted code safely, discover external tools, delegate work, expose control points, and survive long sessions without blowing the context window.

These are the primitives behind Claude Code, Codex, and Copilot. Here you build each one from scratch so you understand exactly what the harness is doing before any framework hides it from you.

## 📚 Tutorials

### [01 - Skills](01-skills/)

Inject specialized capabilities on demand with filesystem-based Agent Skills. A `SKILL.md` catalog stays cheap in the system prompt; full instructions and bundled assets load only when the agent needs them (progressive disclosure).

---

### [02 - Hooks & Lifecycle](02-hooks-lifecycle/)

Intercept the loop at its seams — pre/post tool-use and stop events. Add logging, guardrails, and approval gates as pluggable callbacks instead of rewriting the loop. This is the extensibility surface every later tutorial plugs into.

---

### [03 - Sandboxing](03-sandboxing/)

Run agent-generated code and tool calls in isolation. Subprocess with resource limits, stripped environment, and timeouts as the portable baseline; container isolation as the real boundary.

---

### [04 - MCP Integration](04-mcp/)

Discover tools from Model Context Protocol servers instead of hand-coding them — and publish your own. Bridge MCP tool schemas into the agent loop for both Anthropic and OpenAI.

---

### [05 - Subagents & Delegation](05-subagents/)

Let a parent loop spawn child loops with isolated context that run a subtask to completion and return only a summary. Manage depth, fan-out, and aggregated token usage.

---

### [06 - Context Compaction](06-context-compaction/)

Keep long-running loops alive by compacting their own history — summarizing old turns while pinning the system prompt and task, and never splitting a tool call from its result. Builds on [Context Engineering](../03-advanced-techniques/03-context-engineering/).

---

### [07 - Extensible Agent](07-extensible-agent/) 🏆

**Capstone** — one agent wired with hooks, a sandboxed executor, MCP-discovered tools, subagent delegation, and automatic compaction. Clean composition of every primitive in the module.

---

## 🔗 Resources

- [Agent Skills (Anthropic)](https://www.anthropic.com/news/skills)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [Building Effective Agents (Anthropic)](https://www.anthropic.com/engineering/building-effective-agents)
- [gVisor — sandboxed container runtime](https://gvisor.dev/)
