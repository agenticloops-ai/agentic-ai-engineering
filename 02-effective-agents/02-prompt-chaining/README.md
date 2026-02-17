<!-- ---
title: "Prompt Chaining"
description: "Decompose tasks into sequential LLM calls where each step builds on the previous"
icon: "link"
--- -->

# Prompt Chaining — The Blog Assembly Line

Decompose a task into a sequence of fixed steps, where each LLM call processes the output of the previous one. Simple, linear, and predictable — though individual steps can use tools like web search for grounded output.

## 🎯 What You'll Learn

- Design multi-step LLM pipelines with clear handoffs between stages
- Pass context and results between sequential calls using focused prompts
- Debug and trace execution through the chain with per-step callbacks and token tracking
- Know when chaining beats a single complex prompt

## 📦 Available Examples

| Provider | File | Description |
|----------|------|-------------|
| ![Anthropic](../../common/badges/anthropic.svg) | [01_prompt_chaining.py](01_prompt_chaining.py) | Blog post assembly line with 3-step chain |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 02-effective-agents/02-prompt-chaining python {script_name}

# Example
uv run --directory 02-effective-agents/02-prompt-chaining python 01_prompt_chaining.py
```

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### Sequential Pipeline

```
Topic → [Outliner/Sonnet] → [Writer/Haiku + 🔍] → [Editor/Sonnet] → Final Post
```

Each step has a focused system prompt and a single responsibility. The output of one step becomes the input of the next.

### Quality Gates

Between steps, validate that the previous step produced usable output. If the outliner returns empty text, abort early rather than sending garbage downstream.

### Dual Model Strategy

The chain uses different models for different steps based on task complexity:

- **Sonnet** (steps 1 & 3): Outlining and editing require nuance and judgment
- **Haiku** (step 2): Writing from a structured outline is more straightforward — a faster, cheaper model works well

This is a practical cost optimization: use the most capable model only where it matters.

### Web Search in the Chain

Step 2 (Writer) has access to Anthropic's built-in web search tool, limited to 3 uses per run:

```python
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
```

The model decides autonomously whether to search — the system prompt says "use web search if the topic would benefit from current information." This keeps the chain simple (no explicit search logic) while enabling grounded, up-to-date content.

### Step Design

- **Outliner** (Sonnet): Generate structure (title + 5 bullet points)
- **Writer** (Haiku + web search): Expand outline into full blog post, 2-3 paragraphs per section
- **Editor** (Sonnet): Polish grammar, clarity, and flow; add a Key Takeaways section

Each prompt is optimized for its specific task — not a single "do everything" prompt.

### When to Chain vs. Single Prompt

Chaining adds complexity — use it when the benefits outweigh the cost:

- **Chain when** steps have different requirements (models, tools, temperature), when intermediate output needs validation, or when debugging requires visibility into each stage
- **Single prompt when** the task is straightforward enough that one well-crafted prompt handles it reliably — adding steps just adds latency and failure points

In this tutorial, chaining wins because each step genuinely benefits from a different setup: the outliner needs precision (Sonnet), the writer needs web access (Haiku + search), and the editor needs judgment (Sonnet).

## ⚠️ Important Considerations

- Chain length matters — each step adds latency and token cost
- Errors compound: a bad outline produces a bad article no matter how good the writer prompt is
- Web search adds latency and non-determinism — the same topic may produce different articles based on search results
- Consider adding validation/gates between steps for production use

## 👉 Next Steps

- [03 - Routing](../03-routing/) — add input classification to route to specialized chains
- Experiment: add a 4th step (e.g., SEO optimizer or fact-checker)
