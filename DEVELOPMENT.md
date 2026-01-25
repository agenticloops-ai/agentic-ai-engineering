# Contributing Guide

This guide covers the development workflow, code quality standards, and best practices for contributing to this repository.

## 🚀 Development Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dev dependencies
uv sync

# Verify setup
make check
```

## 🔄 Development Workflow

### Creating a New Lesson

```bash
# 1. Create lesson directory structure
mkdir -p 02-advanced/01-my-lesson

# 2. Create pyproject.toml
cat > 02-advanced/01-my-lesson/pyproject.toml <<EOF
[project]
name = "01-my-lesson"
version = "0.1.0"
description = "Lesson: My Lesson Topic"
requires-python = ">=3.11"
dependencies = [
    # Add lesson-specific dependencies here
    "requests>=2.31.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"
EOF

# 3. Create README.md for the lesson
cat > 02-advanced/01-my-lesson/README.md <<EOF
# My Lesson Topic

## Learning Objectives
- Objective 1
- Objective 2

EOF

# 4. Create your Python scripts
touch 02-advanced/01-my-lesson/script1.py

# 5. Install dependencies and test
cd 02-advanced/01-my-lesson
uv sync
uv run python script1.py
```

### Adding Dependencies to a Lesson

```bash
cd 01-foundations/02-chat

# Option 1: Use uv add (recommended)
uv add pandas

# Option 2: Edit pyproject.toml manually
# Add "pandas>=2.1.0" to dependencies array
# Then run: uv sync
```

### Interactive Development

Use iPython for interactive exploration and experimentation with lesson dependencies:

```bash
# Start iPython with lesson dependencies available
cd 01-foundations/05-agent-loop
uv sync
uv run ipython

# Now you can import and use lesson dependencies interactively
>>> from anthropic import Anthropic
>>> from openai import OpenAI
>>> # Test agent functionality interactively
```

This is useful for:
- Testing code snippets before adding them to scripts
- Exploring library APIs and documentation
- Debugging and experimentation
- Learning new libraries interactively

### Testing Your Changes

```bash
# Test a specific lesson
cd 01-foundations/01-simple-llm-call
uv sync
uv run python llm_call_anthropic.py

# Or use uv run --directory from root
uv run --directory 01-foundations/01-simple-llm-call python llm_call_anthropic.py

# Clean and rebuild all lessons
make clean
make sync-all
```

## ✨ Code Quality Standards

### Quick Commands

```bash
make check    # Run all quality checks (lint, format, types)
make fix      # Auto-fix lint and format issues
make verify   # Verify all scripts compile and imports work
```

### Tools Overview

#### 1. Ruff - Fast Linter & Formatter

Ruff is a lightning-fast Python linter and formatter that replaces Flake8, isort, Black, and more.

**What Ruff Checks:**
- **E/W**: PEP 8 style violations
- **F**: Logical errors (undefined names, unused imports)
- **I**: Import sorting
- **N**: Naming conventions (snake_case, PascalCase)
- **UP**: Modern Python syntax upgrades
- **B**: Common bugs (mutable defaults, etc.)
- **C4**: List/dict comprehension improvements
- **SIM**: Code simplification opportunities
- **PTH**: Prefer pathlib over os.path
- **RUF**: Ruff-specific best practices

**Usage:**

```bash
# Check all modules (via Makefile)
make lint-all

# Auto-fix issues
make lint-fix

# Format code
make format-all

# Check a specific lesson
cd 01-foundations/02-prompt-engineering
uv run ruff check *.py
uv run ruff format *.py
```

#### 2. MyPy - Static Type Checker

MyPy catches type errors before runtime and improves code documentation.

**Usage:**

```bash
# Type check all modules (via Makefile)
make type-check

# Type check specific lesson
cd 01-foundations/04-tool-use
uv run mypy *.py
```

**Best Practice: Use Type Hints**

```python
# Bad - no type hints
def greet(name):
    return f"Hello, {name}"

# Good - with type hints
def greet(name: str) -> str:
    return f"Hello, {name}"
```

#### 3. Pytest - Testing Framework

Write tests for complex lessons or reusable functions.

**Usage:**

```bash
# Create test directory
cd 01-foundations/05-agent-loop
mkdir -p tests
touch tests/test_agent.py

# Run tests
uv run pytest tests/

# Run with coverage
uv run pytest tests/ --cov=. --cov-report=html

# Run all tests in repository
make test-all
```

**Example Test:**

```python
# tests/test_example.py
def add_numbers(a: int, b: int) -> int:
    return a + b

def test_add_numbers():
    assert add_numbers(2, 3) == 5
    assert add_numbers(-1, 1) == 0
```

## 🎨 Code Style Guidelines

### Line Length
- Maximum: **100 characters**
- Configured in `pyproject.toml`

### Import Organization

Ruff automatically sorts imports in this order:
1. Standard library
2. Third-party packages
3. Local/project imports

```python
# Good
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from my_module import my_function
```

### Naming Conventions

```python
# Constants
MAX_RETRIES = 3
API_ENDPOINT = "https://api.example.com"

# Classes
class DataProcessor:
    pass

# Functions and variables
def process_data(input_file: str) -> None:
    user_count = 0
    file_path = Path(input_file)
```

### String Quotes
- Use **double quotes** for strings: `"hello"`
- Configured in Ruff settings

### Avoid Common Pitfalls

```python
# Bad - mutable default argument
def add_item(item, items=[]):
    items.append(item)
    return items

# Good
def add_item(item: str, items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    items.append(item)
    return items

# Bad - unused imports
import os
import sys

def hello():
    print("hello")

# Good - remove unused imports
def hello():
    print("hello")
```

## 📝 Commit Message Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/) for clear and standardized commit messages.

### Types

- **feat**: New feature (e.g., `feat(tutorials): add streaming API examples`)
- **fix**: Bug fix (e.g., `fix(setup): correct environment variable loading`)
- **docs**: Documentation changes (e.g., `docs(readme): update installation steps`)
- **style**: Code style changes (formatting, missing semicolons, etc.)
- **refactor**: Code refactoring without changing functionality
- **perf**: Performance improvements
- **test**: Adding or updating tests
- **build**: Build system or dependencies (e.g., `build(deps): upgrade anthropic to 0.40.0`)
- **ci**: CI/CD configuration changes
- **chore**: Other changes (maintenance, configs, etc.)

### Examples

```bash
# Feature
git commit -m "feat(foundations): add LiteLLM integration example"

# Bug fix
git commit -m "fix(chat): handle empty message history correctly"

# Documentation
git commit -m "docs(contributing): add conventional commits guide"

# Breaking change
git commit -m "feat(api)!: change response format to JSON

BREAKING CHANGE: API responses now return JSON instead of plain text"

# With scope and body
git commit -m "refactor(agent-loop): simplify tool selection logic

- Extract tool matching into separate function
- Add type hints for better IDE support
- Update docstrings"
```

### Quick Tips

- Keep subject line under 72 characters
- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter of subject
- No period at the end of subject
- Use body to explain **what** and **why**, not **how**

## ⚙️ Pre-commit Hooks

Pre-commit hooks automatically run quality checks before each commit.

### Installation

```bash
# Install pre-commit hooks (run once)
uv tool install pre-commit
pre-commit install

# Install commit message hook for conventional commits
pre-commit install --hook-type commit-msg
```

### What Gets Checked

When you commit, these checks run automatically:
1. ✅ **Conventional commit format** (commit message validation)
2. ✅ Ruff linter (with auto-fix)
3. ✅ Ruff formatter
4. ✅ MyPy type checker
5. ✅ Trailing whitespace removal
6. ✅ End-of-file fixer
7. ✅ YAML/TOML/JSON syntax validation
8. ✅ Large file detection
9. ✅ Debug statement detection
10. ✅ Private key detection

### Manual Execution

```bash
# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff --all-files

# Check commit message format
pre-commit run conventional-pre-commit --hook-stage commit-msg --commit-msg-filename .git/COMMIT_EDITMSG

# Update hook versions
pre-commit autoupdate
```

### Common Commit Message Validation Errors

```bash
# ❌ Bad - missing type
git commit -m "update readme"
# Error: Commit message does not follow Conventional Commits format

# ✅ Good
git commit -m "docs(readme): update setup instructions"

# ❌ Bad - capitalized subject
git commit -m "feat: Add new feature"
# Error: Subject should not be capitalized

# ✅ Good
git commit -m "feat: add new feature"

# ❌ Bad - period at end
git commit -m "fix: resolve import error."
# Error: Subject should not end with period

# ✅ Good
git commit -m "fix: resolve import error"
```

### Skip Hooks (Use Sparingly)

```bash
# Only use for emergencies - skips ALL hooks including commit message validation
git commit --no-verify -m "Emergency fix"
```

## 🤖 CI/CD Pipeline

GitHub Actions automatically runs quality checks on:
- Every push to main/develop
- Every pull request
- Manual workflow dispatch

### CI Jobs

1. **Code Quality**
   - Ruff linter
   - Ruff formatter check
   - MyPy type checking
   - Tests on Python 3.11 and 3.12

2. **Lesson Testing**
   - Runs all scripts in each lesson
   - Ensures no runtime errors

3. **Pre-commit**
   - Runs all pre-commit hooks
   - Ensures consistency

## 🔐 Virtual Environment Details

### How It Works

Each lesson has its own isolated virtual environment:

```
01-foundations/01-simple-llm-call/
├── .venv/                    # Isolated virtual environment
├── pyproject.toml            # Lesson dependencies
├── uv.lock                   # Locked versions
├── llm_call_anthropic.py     # Python scripts
└── llm_call_openai.py
```

### Using `uv run` (Recommended)

```bash
cd 01-foundations/02-chat
uv sync
uv run python chat_anthropic.py  # uv automatically uses the lesson's venv
```

### Manual Activation (Alternative)

```bash
cd 01-foundations/04-tool-use
uv sync

# Linux/macOS
source .venv/bin/activate
python tool_use_anthropic.py
deactivate

# Windows
.venv\Scripts\activate
python tool_use_anthropic.py
deactivate
```

### Best Practices

✅ **DO:**
- Use `uv run` for most tasks
- Run `uv sync` after adding dependencies
- Commit `uv.lock` files for reproducibility
- Keep `.venv` in `.gitignore`

❌ **DON'T:**
- Activate multiple venvs at once
- Manually install packages with pip (use `uv add`)
- Share venvs between lessons
- Forget to deactivate when switching lessons (if using manual activation)

### Troubleshooting

**Module not found:**
```bash
cd 01-foundations/05-agent-loop
uv sync
uv run python agent_loop_anthropic.py
```

**Wrong Python version:**
```bash
# Check pyproject.toml: requires-python = ">=3.11"
uv run python --version
```

**Corrupted venv:**
```bash
rm -rf .venv
uv sync
```

## 📊 Common Issues and Fixes

### Issue: Unused Imports

```python
# Ruff reports: F401 'os' imported but unused
import os
import sys

def hello():
    print("hello")
```

**Fix:**
```bash
uv run ruff check --fix 01-foundations/02-chat/chat_anthropic.py
```

### Issue: Lines Too Long

```python
# Line exceeds 100 characters
some_very_long_variable = function_with_many_args(arg1, arg2, arg3, arg4, arg5)
```

**Fix:**
```bash
uv run ruff format 01-foundations/03-prompt-engineering/prompt_engineering_openai.py
```

### Issue: Missing Type Hints

```python
# MyPy warning: Function is missing a type annotation
def calculate(x, y):
    return x + y
```

**Fix:**
```python
def calculate(x: int, y: int) -> int:
    return x + y
```

## 🎯 Best Practices for Contributors

### 1. Keep Functions Small and Focused

```python
# Good - single responsibility
def create_user(data: dict) -> User:
    """Create a user from data dictionary."""
    return User(**data)

# Bad - does too much
def process_user(data):
    user = create_user(data)
    send_email(user)
    log_event(user)
    update_database(user)
    return user
```

### 2. Write Descriptive Names

```python
# Bad
def f(x):
    return x * 2

# Good
def double_value(number: int) -> int:
    return number * 2
```

### 3. Add Docstrings for Complex Functions

```python
def fetch_and_parse_data(url: str, timeout: int = 30) -> dict:
    """Fetch data from URL and parse as JSON.

    Args:
        url: The URL to fetch data from
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Parsed JSON data as dictionary

    Raises:
        RequestException: If the request fails
        JSONDecodeError: If response is not valid JSON
    """
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()
```

### 4. Run Checks Before Committing

```bash
# Quick check before commit
make check-all

# Or rely on pre-commit hooks (automatic)
git add .
git commit -m "Add new lesson"
# Pre-commit hooks run automatically!
```

### 5. Keep Lessons Independent

- Each lesson should be self-contained
- Don't import code from other lessons
- Duplicate small utilities if needed
- Each lesson should run independently

## 🚦 Quick Reference

| Task | Command |
|------|---------|
| **Setup** | `uv sync` |
| **Run all checks** | `make check` |
| **Auto-fix issues** | `make fix` |
| **Verify scripts** | `make verify` |
| **Sync all lessons** | `make sync-all` |
| **Clean caches** | `make clean` |

## 📚 Additional Resources

- [Ruff](https://docs.astral.sh/ruff/) - Linter & formatter
- [MyPy](https://mypy.readthedocs.io/) - Type checker
- [UV](https://docs.astral.sh/uv/) - Package manager

## 💡 Tips for Contributors

1. **Start Small**: Make one change at a time
2. **Run Checks Frequently**: Catch issues early
3. **Read Error Messages**: They're usually helpful!
4. **Use Auto-fix**: Let tools fix what they can
5. **Ask Questions**: Open an issue if you're stuck
6. **Write Tests**: For complex functionality
7. **Keep It Simple**: Avoid over-engineering

---

**Remember**: Code quality tools are here to help, not to gatekeep. They save time and make the codebase better for everyone!
