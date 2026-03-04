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
Context Engineering
    ↓
  (adds persistence)
    ↓
Memory
    ↓
  (adds cost reduction)
    ↓
Cost Optimization
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

### [03 - Context Engineering](03-context-engineering/)

Manage finite context windows with token counting, budget allocation, and automatic compression. Measure tokens precisely, allocate budgets across system prompt, history, and response reserve, and compress automatically when you're running out of room.

---

### [03 - Memory](03-memory/)

Give agents memory that persists across sessions. Short-term conversation buffers, long-term vector stores, and hybrid approaches.

---

### [04 - Cost Optimization](04-cost-optimization/)

Two strategies for reducing API costs. **Prompt caching** marks static system prompt content with cache breakpoints so repeated calls read from cache at 90% savings. **Model routing** classifies task difficulty with a cheap model (Haiku) and routes easy tasks there instead of always using Sonnet — saving ~73% on input for simple queries.

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
