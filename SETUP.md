# Setup Guide

Complete setup instructions for the AI Agents tutorials.

## Prerequisites

- **Python 3.11 or higher**
- **API Keys** from one or both providers:
  - **Anthropic**: [console.anthropic.com](https://console.anthropic.com/)
  - **OpenAI**: [platform.openai.com](https://platform.openai.com/api-keys)

## 1. Install UV

[uv](https://github.com/astral-sh/uv) is a fast Python package manager. Install it first:

```bash
# macOS (Homebrew)
brew install uv

# macOS/Linux (standalone installer)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## 2. Clone the Repository

```bash
git clone https://github.com/agenticloops-ai/agentic-ai-engineering.git
cd agentic-ai-engineering
```

## 3. Set Up Environment Variables

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your API keys
# ANTHROPIC_API_KEY=your_anthropic_key_here
# OPENAI_API_KEY=your_openai_key_here
```

You only need to set keys for the provider(s) you want to use.

## 4. Run Your First Lesson

```bash
cd 01-foundations/01-simple-llm-call
uv sync
uv run 01_llm_call_anthropic.py   # or 02_llm_call_openai.py
```

## Running Lessons

### Interactive Menu

```bash
uv run menu
```

Navigate with arrow keys, press Enter to run scripts.

### Direct Execution

```bash
# From lesson directory
cd 01-foundations/01-simple-llm-call
uv sync
uv run 01_llm_call_anthropic.py

# From root directory
uv run --directory 01-foundations/01-simple-llm-call python 01_llm_call_anthropic.py
```

### VS Code Code Runner

If you have the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) extension installed:

1. Open any Python script in VS Code
2. Click the **Run Code** button (▶️) in the top-right corner, or press `Ctrl+Alt+N` (Windows/Linux) or `Cmd+Alt+N` (macOS)
3. The script will execute in the integrated terminal using `uv run`

Make sure Code Runner is configured to use `uv run` in your VS Code settings.

## Troubleshooting

### "Module not found" error

```bash
cd 01-foundations/01-simple-llm-call
uv sync
```

### Import errors

Always use `uv run` to execute scripts:

```bash
uv run script.py           # Correct
python script.py           # Wrong (unless venv is activated)
```

### Lock file out of sync

```bash
uv lock
uv sync
```

### API key errors

Check that your `.env` file exists and contains valid keys:

```bash
cat .env
# Should show: ANTHROPIC_API_KEY=sk-ant-...
```

## Virtual Environments

Each lesson has its own isolated environment in `.venv/`. You don't need to manage these manually - `uv sync` and `uv run` handle everything.

If you prefer manual activation:

```bash
cd 01-foundations/02-chat
uv sync
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
python chat_anthropic.py
deactivate
```

## Next Steps

- Progress through lessons in order
- See [DEVELOPMENT.md](DEVELOPMENT.md) for contributing
