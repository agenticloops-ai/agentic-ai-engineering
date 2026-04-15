# 🎤 Live Workshop Script — Build an Agent with Claude Code

Companion to [`workshop.md`](workshop.md).

A minimal-prompt sequence for building an agent **live** during the workshop using Claude Code. Each stage is a short prompt that evolves a single `agent.py` file in place — small enough for Claude Code to fill in the gaps, which is itself part of the lesson.

> **Narrative arc:** every stage has a failure that the next stage fixes.
> LLM → no memory → Chat → no world access → Tools → single-turn → Agent Loop → expensive → Context Engineering.

---

## 🎬 Setup (run once)

```
Create pyproject.toml (anthropic, python-dotenv, rich, requests) and a .env with ANTHROPIC_API_KEY placeholder.
```

---

## 1️⃣ Simple LLM Call

**Prompt to Claude Code:**

```
Create agent.py — read one prompt from input(), send it to claude-sonnet-4-6, print the response, then exit. No loop.
```

**Live demo:**
- Run it → *"My name is Alex"*
- Run it again → *"What's my name?"*
- ❌ **No memory.** → motivates Chat.

---

## 2️⃣ Add Chat

**Prompt to Claude Code:**

```
Make it a chat — keep history across turns, loop until 'quit'.
```

**Live demo (two parts):**
- *"My name is Alex"* → *"What's my name?"* → ✅ memory works
- *"What's the weather in Warsaw right now?"* → ❌ hallucinates or refuses → motivates Tools.

---

## 3️⃣ Add Tool Use — Weather

**Prompt to Claude Code:**

```
Add a get_weather(city) tool using open-meteo's free API (no key needed).
```

**Live demo:**
- *"What's the weather in Warsaw?"* → real data now.
- *"And in Paris?"* → chat + tools compose nicely.

---

## 4️⃣ Add read_file

**Prompt to Claude Code:**

```
Add a read_file(path) tool.
```

**Live demo:**
- *"Summarize pyproject.toml"* — grounded in local files. Still single-turn.

---

## 5️⃣ Agent Loop + bash

**Prompt to Claude Code:**

```
Turn it into an agent: loop tool calls until done. Add a bash tool, with a confirm prompt before running.
```

**Live demo:**
- *"Find all Python files and tell me which uses the most imports"*
- Watch it chain `bash` + `read_file` autonomously, with human-in-the-loop approval for each bash call.

---

## 6️⃣ (Bonus) Context Pollution

**Prompt to Claude Code:**

```
Print input tokens after every call.
```

**Live demo:**
- Run the stage-5 prompt twice.
- Watch input tokens balloon as history + tool schemas accumulate.
- Land the MCP / Skills punchline: **every tool you add costs tokens on every turn.**

---

## 🎯 The Narrative Arc

| Stage | What breaks | What fixes it next |
|---|---|---|
| 1 LLM Call | No memory | → Chat |
| 2 Chat | Can't see the world | → Tools |
| 3 Weather tool | One tool, one question | → More tools |
| 4 read_file | Still single-turn | → Agent loop |
| 5 Agent loop | Works… but expensive | → Context engineering (MCP / Skills) |

Every stage earns its existence by solving the pain of the previous one.

---

## 🧑‍🏫 Teaching Tips

- **Keep files visible** — editor next to terminal, so attendees watch `agent.py` grow from ~15 → ~60 lines.
- **If Claude Code over-engineers**, say *"make it simpler, single file, minimal abstractions"*.
- **Run `git diff` between stages** — the delta is the lesson.
- **Break it on purpose** — drop the `max_iterations` bound and ask it to "list every file recursively forever" to show why bounds matter.
- **Compare to the repo** — after stage 5, open [`01-foundations/05-agent-loop/01_minimal_agent.py`](05-agent-loop/01_minimal_agent.py) to show a production-shaped ~55-line version.
- **Short prompts are the point** — Claude Code fills in idioms, error handling, schema shapes. That's the same thing an *agent* does: act on intent, not specs.
