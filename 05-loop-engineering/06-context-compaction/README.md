<!-- ---
title: "Context Compaction"
description: "Keep long-running loops alive by compacting their own history mid-run"
icon: "scissors"
status: "coming-soon"
--- -->

# Context Compaction

Long-running loops eventually outgrow the context window. Compaction lets the agent summarize its own old turns mid-run — pinning the system prompt and task, and never splitting a tool call from its result — so the loop survives many iterations.

## 🎯 What You'll Learn

- Trigger compaction as a loop-lifecycle event with a `should_compact()` check
- Summarize old turns while pinning the system prompt and current task
- Preserve `tool_use`/`tool_result` pairing to avoid API errors
- Handle compaction on the OpenAI Responses API by resending a compacted input

> 🚧 **Coming soon** — [Subscribe to our Substack](https://agenticloopsai.substack.com) or ⭐️ star the repo to get notified when this tutorial drops. See also [Context Engineering](../../03-advanced-techniques/03-context-engineering/).
