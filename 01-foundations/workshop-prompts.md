# 🎤 Live Workshop Script — Build an Agent with Claude Code

Companion to [`workshop.md`](workshop.md).

A minimal-prompt sequence for building an agent **live** during the workshop using Claude Code. Each stage is a short prompt that evolves a single `agent.py` file in place — small enough for Claude Code to fill in the gaps, which is itself part of the lesson.

> **Narrative arc:** every stage has a failure that the next stage fixes.
> Stateless loop → no memory → Chat → no world access → Tools → one tool isn't enough → More tools → manual orchestration → Agent loop + HITL.

---

## 🎬 Setup (run once)

```
Create pyproject.toml (anthropic, python-dotenv, rich) and a .env with ANTHROPIC_API_KEY placeholder.
```

> 💡 If you have a preferred LLM logging / token-tracking lib, drop it in now and ask Claude Code to wire it into every LLM call.

---

## 1️⃣ Stateless Loop — No Memory

**Prompt to Claude Code:**

```
Create agent.py — loop: read user input, call claude-sonnet-4-6, print response. Do not keep any history between turns.
```

**Goal:** show that the model has no memory.

**Live demo:**
- *"What is an AI agent?"* → gets a fine answer.
- *"My name is Alex"* → acknowledges.
- *"What's my name?"* → ❌ **has no idea.** → motivates Chat.

---

## 2️⃣ Add Chat — Pass Context

**Prompt to Claude Code:**

```
Add chat history — keep all turns and send them on every call.
```

**Goal:** show how context is passed to the LLM.

**Live demo:**
- *"My name is Alex"* → *"What's my name?"* → ✅ memory works.
- *"Summarize dependencies in pyproject.toml"* → ❌ **can't read files.** → motivates Tools.

---

## 3️⃣ Add read_file Tool — Interact With the Environment

**Prompt to Claude Code:**

```
Add a read_file(path) tool.
```

**Goal:** show how the agent can interact with the environment.

**Live demo:**
- *"Summarize dependencies in pyproject.toml"* → ✅ reads and summarizes.
- *"List project files"* → ❌ **read_file can't list directories.** → motivates more tools.

---

## 4️⃣ Add bash + write_file Tools

**Prompt to Claude Code:**

```
Add two tools: bash (run shell command) and write_file (path, content).
```

**Goal:** show how multiple tools compose into real work.

**Live demo:**
- *"List project files"* → uses `bash`.
- *"Create a README with a one-line description of this project"* → uses `read_file` + `write_file`.

### 4.1 Human-in-the-Loop

**Prompt to Claude Code:**

```
Before running bash, ask the user to confirm with y/n.
```

**Goal:** safety guardrail for destructive actions.

**Live demo:**
- *"Delete all .pyc files"* → agent proposes `find ... -delete`, waits for approval.

---

## 🎯 The Narrative Arc

| Stage | What breaks | What fixes it next |
|---|---|---|
| 1 Stateless loop | No memory | → Chat |
| 2 Chat | Can't see the world | → read_file |
| 3 read_file | One tool isn't enough | → bash + write_file |
| 4 Multi-tool agent | No safety on destructive actions | → Human-in-the-loop |

Every stage earns its existence by solving the pain of the previous one.

---

## 🧑‍🏫 Teaching Tips

- **Keep files visible** — editor next to terminal, so attendees watch `agent.py` grow from ~15 → ~60 lines.
- **If Claude Code over-engineers**, say *"make it simpler, single file, minimal abstractions"*.
- **Run `git diff` between stages** — the delta is the lesson.
- **Compare to the repo** — after stage 4, open [`05-agent-loop/01_minimal_agent.py`](05-agent-loop/01_minimal_agent.py) to show a production-shaped ~55-line version.
- **Short prompts are the point** — Claude Code fills in idioms, error handling, schema shapes. That's the same thing an *agent* does: act on intent, not specs.
