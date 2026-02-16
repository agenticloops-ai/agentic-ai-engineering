# CLAUDE.md — Agent Rules for AI Agents Engineering

## Project Overview

Educational tutorial repository teaching AI agent engineering through progressive lessons.

A practical, hands-on guide to AI agent development. Learn by building real agents — from basic LLM interactions to autonomous tool-using systems. Master agentic patterns, explore popular frameworks, and discover deployment strategies through interactive tutorials.

Each lesson contains Python scripts demonstrating the corresponding concept(s).

## Repository Structure

```
01-foundations/          # Each module (numbered, progressive) consists of multiple tutorials + module README.md
  01-simple-llm-call/    # Each tutorial has numbered Python scripts + tutorial README.md
  02-prompt-engineering/
  03-chat/
  04-tool-use/
  05-agent-loop/
  README.md.             #
02-advanced/
  01-new-tutorial
  ...
  README.md
common/src/common/       # Shared utilities (logging, token tracking)
```

## Python Script Rules

### Naming

- Scripts use numbered prefixes by provider: `01_*_anthropic.py`, `02_*_openai.py`, `03_*_litellm.py`
- Names are lowercase with underscores

### Code Structure (in order)

1. Module-level docstring
2. Imports: stdlib → third-party → local (`from common`)
3. Environment setup: `load_dotenv(find_dotenv())`
4. Logging: `from common.logging_config import setup_logging; logger = setup_logging(__name__)`
5. Constants (e.g., `TOOLS`, `BLOCKED_COMMANDS`)
6. Utility functions
7. Main class encapsulating agent/session logic
8. `def main() -> None:` orchestration function
9. `if __name__ == "__main__": main()`

### Style

- PEP 8 with **100-character line length**
- Python **3.11+** target
- **Double quotes** for strings
- **Type hints** on all function signatures (`def method(param: str) -> str`)
- **Docstrings** on classes and public methods but without argumets to keep it short - prefer one line when possible
- **Logging** via `logger` — never use `print()` for operational output
- **Rich** library for interactive terminal UI (panels, markdown, colored text) - use in orchestration function only
- **No unnecessary comments** — avoid unnecessary comments - use comments to highlight tutorial concepts, important code blocks or for non-obvious code

### Patterns

- Each script is **self-contained** and independently runnable
- Always encapsulate LLM logic in a **class** (e.g., `LLMClient`, `Chat`, `Agent`)
- Use **token tracking** from `common.token_tracking` — track per call, report at session end
- Use **try/except** with `logger.error()` for error handling
- Tool-use scripts must include **safety guardrails** (e.g., blocked commands list)

### Dependencies

Every tutorial is independent and has own `pyproject.toml` that includes:

- required dependencies, e.g. `anthropic>=0.40.0`, `openai>=1.0.0`, `python-dotenv>=1.0.0`, `rich>=13.7.0`
- `common` as editable local path: `{ path = "../../common", editable = true }`

## README Rules

### Module README Structure (e.g., `01-foundations/README.md`)

Header
```yaml
---
title: "Title"
description: "Brief description"
---
```

1. **Title & Introduction** — module name and one-line summary
2. **🗺️ Progression Path** — ASCII diagram showing tutorial flow and what each step adds
3. **💡 Tips for Success** — numbered list of practical advice
4. **📚 Tutorials** — one section per tutorial with heading link, "What you'll learn" bullets, and "Evolution" note describing what it adds over the previous tutorial
5. **🔗 Resources** — grouped external links (e.g. Anthropic docs, OpenAI docs, etc.)

### Tutorial README Structure (e.g., `01-simple-llm-call/README.md`)

Header
```yaml
---
title: "Title"
description: "Brief description"
icon: "icon name"
---
```

1. **Title & Introduction** — what you'll learn
2. **🎯 What You'll Learn** — bullet list of learning objectives
3. **📦 Available Examples** — table of implementations
4. **🚀 Quick Start** — prerequisites note linking to SETUP.md, `uv run --directory` command pattern with example, Code Runner mention
5. **🔑 Key Concepts** — detailed explanations with code examples showing key concepts for the tutorial, reference to previous tutorials instead of duplicating
6. **🏗️ Code Structure** — optional, architecture patterns (for complex tutorials)
7. **⚠️ Important Considerations** — production concerns and gotchas
8. **👉 Next Steps** — link to next tutorial + suggested experiments

## Mermaid Diagrams

- Use **only when a visual flow adds clarity** — not every tutorial needs a diagram
- Best suited for: data flows, loop patterns, decision trees, multi-step architectures
- Skip diagrams for: simple linear concepts, single API calls that are self-explanatory
- Use **handDrawn look** with **neutral theme** for consistent style:
  ```
  ---
  config:
    look: handDrawn
    theme: neutral
  ---
  ```
- Add **emoji icons** to nodes: `🧠` LLM, `🔧` tools, `📝` storage, `🗣️` input, `📄` output, `⚙️` logic, `💬` display
- Add **edge labels** with engineering verbs (`request`, `response`, `iterate`, `evaluate`, `append`)
- **Pad node text** with trailing spaces to normalize widths across nodes
- Use `"LLM Call"` not `"Send to LLM"` — prefer technical, concise labels

## Code Quality

- **Linter**: ruff (rules: F, E, W, I, N, UP, B, C4, SIM, PTH, RUF)
- **Formatter**: black / ruff format
- **Type checker**: mypy
- **Run checks**: `make check`, `make lint-all`, `make format-check`
- **Run scripts**: `make run`
- **Sync deps**: `uv sync`

## Git

- Use **conventional commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Pre-commit hooks enforce linting and formatting
