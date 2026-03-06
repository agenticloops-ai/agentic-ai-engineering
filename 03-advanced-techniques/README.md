<!-- ---
title: "Advanced Techniques"
description: "Practical engineering problems you'll hit the moment agents leave the prototype stage — solved one tutorial at a time"
--- -->

# Advanced Techniques

Practical engineering problems you'll hit the moment agents leave the prototype stage. Context limits, cost, memory, multimodal input — solved one tutorial at a time.

> **Coming soon** — this module is under active development. [Subscribe to our Substack](https://agenticloopsai.substack.com) or star the repo to get notified when tutorials drop.

## Progression Path

```
Structured Output
    ↓
  (adds real-time output)
    ↓
Streaming
    ↓
  (adds window strategies)
    ↓
Context Engineering
    ↓
  (adds cost reduction)
    ↓
Cost Optimization
    ↓
  (adds persistence)
    ↓
Memory Systems
    ↓
  (adds advanced retrieval)
    ↓
RAG Techniques
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
  (adds safety & quality)
    ↓
Guardrails & Evaluation
```

## Tutorials

### [01 - Structured Output](01-structured-output/)

Force LLM responses into exact schemas — JSON mode, Pydantic models, constrained generation. The bridge between natural language and your application code.

---

### [02 - Streaming](02-streaming/)

SSE, token-by-token output, and streaming tool calls. Every production UI needs this and it's surprisingly tricky to get right with agents.

---

### [03 - Context Engineering](03-context-engineering/)

Manage finite context windows with token counting, budget allocation, and automatic compression. Measure tokens precisely, allocate budgets across system prompt, history, and response reserve, and compress automatically when you're running out of room.

---

### [04 - Cost Optimization](04-cost-optimization/)

Two strategies for reducing API costs. **Prompt caching** marks static system prompt content with cache breakpoints so repeated calls read from cache at 90% savings. **Model routing** classifies task difficulty with a cheap model (Haiku) and routes easy tasks there instead of always using Sonnet — saving ~73% on input for simple queries.

---

### [05 - Memory Systems](05-memory/)

Three-tier agent memory that persists across sessions. Working memory (session buffer), episodic memory (timestamped events in JSON), and semantic memory (facts in ChromaDB vector store) — with agent-driven tools and session consolidation.

---

### [06 - RAG Techniques](06-rag-techniques/)

Retrieval-Augmented Generation for answering questions from external documents. **Pipeline RAG** builds a full ingest → chunk → embed → hybrid retrieve → rerank → generate pipeline. **Agentic RAG** gives the agent a search tool so it decides when to retrieve, what query to use, and whether to search again.

---

### [07 - Multimodal](07-multimodal/)

Move beyond text-only agents. Send images to Claude for vision analysis, generate images with Gemini's native generation, and build voice capabilities with OpenAI's TTS and Whisper. Three scripts, three providers, three modalities.

---

### [08 - MCP (Model Context Protocol)](08-mcp/)

Standardize tool access with the Model Context Protocol. Build an MCP server with FastMCP decorators, connect a Claude-powered agent that discovers tools dynamically, and learn when MCP is worth the overhead vs custom tools — with an honest side-by-side comparison.

---

### [09 - Multi-Agent Systems](09-multi-agent-systems/)

Five coordination patterns for multi-agent systems — pipeline, router, orchestrator-workers, evaluator-optimizer, and debate. Learn when multiple agents outperform a single agent with many tools, and how to manage the cost tradeoffs.

---

### [10 - Guardrails, Safety & Evaluation](10-guardrails-eval/)

The safety layer that separates prototypes from production. **Input guardrails** catch prompt injection, PII, and harmful intent before they reach the agent. **Output guardrails** verify responses for policy violations and hallucination. **LLM-as-judge** scores agent quality with rubric-based evaluation and pairwise comparison. **Red teaming** stress-tests your defenses across six attack categories.

---

## Resources

- [Anthropic Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [Anthropic Vision](https://docs.anthropic.com/en/docs/build-with-claude/vision)
- [Anthropic Guardrails Guide](https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks)
- [Google Gemini Image Generation](https://ai.google.dev/gemini-api/docs/image-generation)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Pre-built MCP Servers](https://github.com/modelcontextprotocol/servers)
- [OpenAI Speech-to-Text](https://platform.openai.com/docs/guides/speech-to-text)
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [OpenAI Text-to-Speech](https://platform.openai.com/docs/guides/text-to-speech)
- [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/)
