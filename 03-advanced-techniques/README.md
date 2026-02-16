<!-- ---
title: "Advanced Techniques"
description: "Practical engineering problems you'll hit the moment agents leave the prototype stage — solved one tutorial at a time"
--- -->

# Advanced Techniques

Practical engineering problems you'll hit the moment agents leave the prototype stage. Context limits, cost, memory, multimodal input — solved one tutorial at a time.

> 🚧 **Coming soon** — this module is under active development. [Subscribe to our Substack](https://agenticloopsai.substack.com) or ⭐️ star the repo to get notified when tutorials drop.

## 🗺️ Progression Path

```
Structured Output
    ↓
  (adds window strategies)
    ↓
Context Management
    ↓
  (adds persistence)
    ↓
Memory
    ↓
  (adds cost reduction)
    ↓
Prompt Caching
    ↓
  (adds non-text input)
    ↓
Multimodal
    ↓
  (adds standardized tools)
    ↓
MCP
    ↓
  (adds agent collaboration)
    ↓
Multi-Agent Systems
    ↓
  (adds advanced retrieval)
    ↓
RAG Techniques
    ↓
  (adds real-time output)
    ↓
Streaming
```

## 📚 Tutorials

### [01 - Structured Output](01-structured-output/)

Force LLM responses into exact schemas — JSON mode, Pydantic models, constrained generation. The bridge between natural language and your application code.

---

### [02 - Context Management](02-context-management/)

Handle the reality of finite context windows. Sliding windows, summarization, chunking strategies, and knowing what to keep vs. what to drop.

---

### [03 - Memory](03-memory/)

Give agents memory that persists across sessions. Short-term conversation buffers, long-term vector stores, and hybrid approaches.

---

### [04 - Prompt Caching](04-prompt-caching/)

Cache static prompt prefixes to cut latency and cost. Understand when caching helps, when it doesn't, and how to structure prompts for maximum reuse.

---

### [05 - Multimodal](05-multimodal/)

Process images, audio, and files alongside text. Build agents that can see screenshots, read documents, and work with the real-world data your users have.

---

### [06 - MCP (Model Context Protocol)](06-mcp/)

Connect agents to external tools through a standardized protocol. Build and consume MCP servers for databases, APIs, file systems, and more.

---

### [07 - Multi-Agent Systems](07-multi-agent-systems/)

Multiple agents collaborating on shared tasks. Communication patterns, delegation, conflict resolution, and when multi-agent is (and isn't) the right call.

---

### [08 - RAG Techniques](08-rag-techniques/)

Move beyond basic vector similarity search. Hybrid retrieval, knowledge graphs, contextual chunking, and agentic RAG patterns for complex queries.

---

### [09 - Streaming](09-streaming/)

SSE, token-by-token output, and streaming tool calls. Every production UI needs this and it's surprisingly tricky to get right with agents.

---

## 🔗 Resources

- [Anthropic Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
