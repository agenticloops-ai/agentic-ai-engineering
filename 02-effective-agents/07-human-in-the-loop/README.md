<!-- ---
title: "Human in the Loop"
description: "Pause agentic workflows at strategic checkpoints for human review, approval, or editing"
icon: "user-check"
--- -->

# Human-in-the-Loop — The Approval Gate

Pause the workflow at strategic checkpoints for human review. The LLM drafts an email, a human approves or rejects with feedback, and the LLM revises — showing where human oversight adds the most value.

## 🎯 What You'll Learn

- Place checkpoints where errors compound most — early in the pipeline
- Implement three response modes: approve, reject with feedback, edit directly
- Inject a checkpoint function into the agent class to keep logic testable
- Cap revision loops to prevent infinite human-agent ping-pong

## 📦 Available Examples

| Provider | File | Description |
|----------|------|-------------|
| ![Anthropic](../../common/badges/anthropic.svg) | [01_human_in_the_loop.py](01_human_in_the_loop.py) | Email drafting with 2 strategic checkpoints |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 02-effective-agents/07-human-in-the-loop python {script_name}

# Example
uv run --directory 02-effective-agents/07-human-in-the-loop python 01_human_in_the_loop.py
```

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### Checkpoint Placement

Two checkpoints, each at a different leverage level:

1. **After draft** — high leverage. Catches wrong tone, missing points, or misunderstood intent before any revision work happens.
2. **After revision** — confirms the feedback was incorporated. If not, the human can provide more feedback (up to `MAX_REVISIONS`).

### Three Response Modes

Each checkpoint offers three options:

- **(y) Approve** — continue with the current output
- **(n) Reject + feedback** — agent revises based on your feedback
- **(e) Edit** — replace the output with your own text directly

This gives the human full control: light-touch (approve), directed (feedback), or hands-on (edit).

### Injectable Checkpoint Function

The `CheckpointFn` type makes the agent testable and adaptable:

```python
CheckpointFn = Callable[[str, str, str], tuple[bool, str]]
```

- In the terminal: `human_checkpoint()` prompts via Rich UI
- In tests: pass a lambda that auto-approves
- In production: replace with a Slack message, webhook, or UI modal

### The Leverage Principle

Early checkpoints have the highest leverage. Catching a wrong tone at checkpoint 1 saves all revision work. Catching a typo at checkpoint 2 saves nothing. Design checkpoints for maximum error prevention, not maximum coverage.

## ⚠️ Important Considerations

- Too many checkpoints = human does all the work (defeats the purpose)
- Too few checkpoints = agent makes uncorrectable mistakes
- In production, checkpoints are async — Slack messages, UI approvals, webhooks — not terminal input
- Cap revision loops (`MAX_REVISIONS`) to prevent unbounded costs

## 👉 Next Steps

- [08 - Full Agent](../08-full-agent/) — combine all patterns into an autonomous agent
- Experiment: add a confidence score to auto-approve high-confidence drafts
- Try replacing `human_checkpoint` with a function that logs to a file (simulating async review)
