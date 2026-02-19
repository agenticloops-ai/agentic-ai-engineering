

<div align="center">

![AI Agents Engineering](common/images/banner.png)

<!-- Keep these links. Translations will automatically update with the README. -->
[English](https://zdoc.app/en/agenticloops-ai/agentic-ai-engineering) | 
[Deutsch](https://zdoc.app/de/agenticloops-ai/agentic-ai-engineering) | 
[Español](https://zdoc.app/es/agenticloops-ai/agentic-ai-engineering) | 
[français](https://zdoc.app/fr/agenticloops-ai/agentic-ai-engineering) | 
[日本語](https://zdoc.app/ja/agenticloops-ai/agentic-ai-engineering) | 
[한국어](https://zdoc.app/ko/agenticloops-ai/agentic-ai-engineering) | 
[Português](https://zdoc.app/pt/agenticloops-ai/agentic-ai-engineering) | 
[中文](https://zdoc.app/zh/agenticloops-ai/agentic-ai-engineering)

[![Website](https://img.shields.io/badge/Website-agenticloops.ai-green?style=for-the-badge&logo=googlechrome&logoColor=white)](https://agenticloops.ai)
[![Substack](https://img.shields.io/badge/Substack-Blogs_&_Newsletter-orange?style=for-the-badge&logo=substack&logoColor=white)](https://agenticloopsai.substack.com)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/agenticloops-ai)
[![Follow @agenticloops_ai](https://img.shields.io/badge/Follow%20%40agenticloops__ai-black?style=for-the-badge&logo=x&logoColor=white)](https://x.com/agenticloops_ai)

</div>

# Agentic AI Engineering
*by [AgenticLoops.ai](https://agenticloops.ai) - for Engineers, from Engineers*

**A practical, hands-on guide to AI agent development**. Learn by building real agents - from basic LLM interactions to autonomous tool-using systems. Master agentic patterns, explore popular frameworks, and discover deployment strategies through interactive tutorials.

📝 **[Subscribe to our Substack](https://agenticloopsai.substack.com)** to get deep-dive engineering posts on AI agents. No hype, just engineering insights.

## 🎯 Who Is This For?

- **Engineers** who want to understand how AI agents work **under the hood** and move beyond chat wrappers... and build tool-using, autonomous agents
- **Anyone** who prefers **learning by running real code** over watching videos or reading theory

No prior AI/ML experience required - just Python basics and **curiosity** about building LLM-powered agents.

**We're starting small but adding new tutorials continuously.** If you find this useful, a ⭐️ star helps us know we're on the right track. Join the [💬 discussion](https://github.com/agenticloops-ai/agentic-ai-engineering/discussions) or report an [🐛 issue](https://github.com/agenticloops-ai/agentic-ai-engineering/issues) - your input directly shapes what we build next.

## 🚀 Quick Start

```bash
brew install uv

git clone https://github.com/agenticloops-ai/agentic-ai-engineering.git

cd agentic-ai-engineering
cp .env.example .env  # add your API keys

uv run --directory 01-foundations/01-simple-llm-call python 01_simple_call_anthropic.py
```

See 📚[SETUP.md](SETUP.md) for detailed setup instructions.

## 🗂️ Tutorials Structure

The tutorials are organized into **modules** (`01-foundations`, `02-effective-agents`) that progress from basics to advanced concepts. Each module contains numbered **tutorials** that build on previous lessons. Inside each tutorial folder, you'll find:

- **Python scripts** ![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white) - Self-contained, runnable examples demonstrating key concepts
- **README.md** - Detailed explanations, code walkthroughs, and learning objectives

You can explore individual scripts independently or follow the complete learning path from start to finish. Each module ends with a ![🏆 capstone](https://img.shields.io/badge/🏆_capstone-blue) project that combines all concepts from the module into a single, production-style agent.

### 🎓 [01 - Foundations](01-foundations/README.md) ![new](https://img.shields.io/badge/new-brightgreen)

Your first steps — from a single API call to a fully autonomous agent loop. Build everything from scratch to understand what's really happening under the hood.

1. **[Simple LLM Call](01-foundations/01-simple-llm-call/)** — First API call with token tracking
2. **[Prompt Engineering](01-foundations/02-prompt-engineering/)** — Guide model behavior
3. **[Chat](01-foundations/03-chat/)** — Interactive chat with message history
4. **[Tool Use](01-foundations/04-tool-use/)** — Enable function calling
5. **[Agent Loop](01-foundations/05-agent-loop/)** — Autonomous tool-using agents
6. **[Codebase Navigator](01-foundations/06-codebase-navigator/)** ![🏆 capstone](https://img.shields.io/badge/🏆_capstone-blue) — The Augmented LLM with RAG, tools, and memory

### 🧩 [02 - Effective Agents Patterns](02-effective-agents/README.md) ![new](https://img.shields.io/badge/new-brightgreen)

Architectural patterns that separate toy demos from real agents. Based on Anthropic's "[Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)" — learn when to chain, route, parallelize, or delegate.

1. **[Prompt Chaining](02-effective-agents/01-prompt-chaining/)** — Sequential multi-step pipelines
2. **[Routing](02-effective-agents/02-routing/)** — Classify input, dispatch to specialized handlers
3. **[Parallelization](02-effective-agents/03-parallelization/)** — Fan-out/fan-in, parallel tool calls
4. **[Orchestrator-Workers](02-effective-agents/04-orchestrator-workers/)** — Dynamic task decomposition
5. **[Evaluator-Optimizer](02-effective-agents/05-evaluator-optimizer/)** — Self-critique, iterative refinement
6. **[Human in the Loop](02-effective-agents/06-human-in-the-loop/)** — Approval gates, escalation, feedback
7. **[Content Writer](02-effective-agents/07-content-writer/)** ![🏆 capstone](https://img.shields.io/badge/🏆_capstone-blue) — Full agent composing all agentic workflow patterns

### 🧬 [03 - Advanced Techniques](03-advanced-techniques/README.md) ![coming soon](https://img.shields.io/badge/coming%20soon-orange)

Practical engineering problems you'll hit the moment agents leave the prototype stage. Context limits, cost, memory, multimodal input — solved one tutorial at a time.

1. **[Structured Output](03-advanced-techniques/01-structured-output/)** — JSON mode, schemas, constrained generation
2. **[Context Management](03-advanced-techniques/02-context-management/)** — Window strategies, summarization, chunking
3. **[Memory](03-advanced-techniques/03-memory/)** — Short-term, long-term, vector stores
4. **[Prompt Caching](03-advanced-techniques/04-prompt-caching/)** — Cache strategies, cost reduction
5. **[Multimodal](03-advanced-techniques/05-multimodal/)** — Vision, audio, file processing
6. **[MCP](03-advanced-techniques/06-mcp/)** — Model Context Protocol, standardized tool integration
7. **[Multi-Agent Systems](03-advanced-techniques/07-multi-agent-systems/)** — Agent-to-agent communication, delegation
8. **[RAG Techniques](03-advanced-techniques/08-rag-techniques/)** — Hybrid search, GraphRAG, agentic retrieval
9. **[Streaming](03-advanced-techniques/09-streaming/)** — SSE, token-by-token output, streaming tool calls

### 🏗️ [04 - Frameworks](04-frameworks/README.md) ![coming soon](https://img.shields.io/badge/coming%20soon-orange)

One agent, nine implementations. Build the same system with each framework and compare trade-offs with your own hands.

1. **[No Framework](04-frameworks/01-no-framework/)** — Raw SDK baseline
2. **[LangGraph](04-frameworks/02-langgraph/)** — Graph-based orchestration
3. **[Pydantic AI](04-frameworks/03-pydantic-ai/)** — Type-safe agents
4. **[Google ADK](04-frameworks/04-google-adk/)** — Google's Agent Development Kit
5. **[AWS Strands](04-frameworks/05-aws-strands/)** — AWS agent SDK
6. **[CrewAI](04-frameworks/06-crewai/)** — Role-based multi-agent collaboration
7. **[AutoGen](04-frameworks/07-autogen/)** — Multi-agent conversations
8. **[LlamaIndex](04-frameworks/08-llamaindex/)** — Data-centric agents
9. **[Semantic Kernel](04-frameworks/09-semantic-kernel/)** — Microsoft AI orchestration

### 🧪 [05 - Testing & Evaluation](05-testing-evaluation/README.md) ![coming soon](https://img.shields.io/badge/coming%20soon-orange)

Agents are non-deterministic — testing them requires different thinking. Measure quality, catch regressions, and build confidence before shipping.

1. **[Unit Testing Agents](05-testing-evaluation/01-unit-testing-agents/)** — Mocking LLMs, deterministic tests
2. **[Evals](05-testing-evaluation/02-evals/)** — Accuracy, quality, regression benchmarks
3. **[Tracing & Debugging](05-testing-evaluation/03-tracing-debugging/)** — Observability during development
4. **[Red Teaming & Safety](05-testing-evaluation/04-red-teaming-safety/)** — Adversarial testing, guardrails
5. **[Benchmarking](05-testing-evaluation/05-benchmarking/)** — Comparing models, prompts, architectures head-to-head

### 🏭 [06 - Production](06-production/README.md) ![coming soon](https://img.shields.io/badge/coming%20soon-orange)

The gap between "works on my laptop" and "runs reliably at scale." Principles, deployment, monitoring, cost control, and security.

1. **[12-Factor Agents](06-production/01-twelve-factor-agents/)** — Principles for production-grade agents
2. **[Deployment Strategies](06-production/02-deployment-strategies/)** — Containers, serverless, scaling
3. **[Monitoring & Observability](06-production/03-monitoring-observability/)** — Metrics, logging, tracing in prod
4. **[Cost Optimization](06-production/04-cost-optimization/)** — Token budgets, caching, model routing
5. **[Security & Guardrails](06-production/05-security-guardrails/)** — Auth, sandboxing, injection defense
6. **[Error Handling & Resilience](06-production/06-error-handling-resilience/)** — Retries, fallbacks, graceful degradation


## 💜 Support Us

If you find this project useful, consider supporting us:

[![Sponsor](https://img.shields.io/badge/Sponsor-Support_Us-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/agenticloops-ai)

## 💬 FAQ

**Module not found?** Run `uv sync` in the lesson directory.

**API errors or authentication failures?** You need API keys from [Anthropic](https://console.anthropic.com/), [OpenAI](https://platform.openai.com/), or both, depending on which examples you run. See [SETUP.md](SETUP.md) for details.


## ⚖️ License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
