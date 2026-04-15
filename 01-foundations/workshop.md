---
marp: true
theme: uncover
class: invert
paginate: true
backgroundColor: #0f1115
color: #e7e9ee
style: |
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Kalam:wght@400;700&display=swap');
  section {
    font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
    background:
      radial-gradient(circle at 10% 0%, rgba(255,180,84,0.08), transparent 40%),
      radial-gradient(circle at 90% 40%, rgba(124,209,255,0.06), transparent 45%),
      #0f1115;
    color: #e7e9ee;
    padding: 50px 60px;
    font-size: 22px;
    line-height: 1.5;
    text-align: left;
    justify-content: flex-start;
    align-items: stretch;
  }
  section > * {
    text-align: left;
  }
  section h1 { text-align: left; }
  section h2 { text-align: left; }
  section h3 { text-align: left; }
  h1 {
    color: #ffb454;
    font-weight: 700;
    letter-spacing: -0.01em;
    border-bottom: 1px dashed #2a2f3a;
    padding-bottom: 10px;
  }
  h2 {
    color: #7cd1ff;
    font-weight: 600;
  }
  h3 {
    color: #7cd1ff;
    text-transform: uppercase;
    font-size: 0.8em;
    letter-spacing: 0.04em;
  }
  strong { color: #ffd27a; }
  em { color: #b4f078; font-style: normal; }
  code {
    background: #0b0d12;
    color: #ffd27a;
    padding: 2px 6px;
    border-radius: 6px;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 0.85em;
    border: 1px solid #2a2f3a;
  }
  pre {
    background: #0b0d12 !important;
    border: 1px solid #2a2f3a;
    border-radius: 10px;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 0.68em;
    padding: 14px 16px;
  }
  pre code {
    background: transparent;
    color: #e7e9ee;
    border: none;
    padding: 0;
  }
  table {
    border-collapse: collapse;
    margin: 0 auto;
    font-size: 0.8em;
  }
  th {
    background: #151821;
    color: #ffb454;
    padding: 8px 14px;
    border: 1px solid #2a2f3a;
  }
  td {
    padding: 8px 14px;
    border: 1px solid #2a2f3a;
  }
  .columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.2rem;
  }
  .pros { color: #b4f078; }
  .cons { color: #ff7a7a; }
  .accent { color: #ffb454; }
  .hand {
    font-family: 'Kalam', 'Caveat', cursive;
    color: #ffb454;
  }
  .eyebrow {
    font-family: 'Kalam', 'Caveat', cursive;
    color: #ffb454;
    font-size: 0.7em;
    letter-spacing: 0.5px;
  }
  .chip {
    display: inline-block;
    font-size: 0.65em;
    background: #151821;
    color: #e7e9ee;
    border: 1px solid #2a2f3a;
    padding: 3px 10px;
    border-radius: 999px;
    margin-right: 4px;
  }
  .chip.warn { border-color: #5a3a1d; color: #ffb454; }
  .chip.danger { border-color: #5a2525; color: #ff7a7a; }
  .chip.ok { border-color: #2c4a25; color: #b4f078; }
  .step-pill {
    display: inline-block;
    background: #ffb454;
    color: #1a1204;
    font-weight: 700;
    font-size: 0.55em;
    padding: 3px 10px;
    border-radius: 999px;
    letter-spacing: 0.05em;
    vertical-align: middle;
    margin-right: 8px;
  }
  .callout {
    border-left: 3px solid #ffb454;
    background: rgba(255,180,84,0.06);
    padding: 12px 16px;
    border-radius: 8px;
    margin: 12px 0;
    color: #efe6d6;
    font-size: 0.85em;
  }
  .callout.danger {
    border-left-color: #ff7a7a;
    background: rgba(255,122,122,0.06);
    color: #f7dcdc;
  }
  .callout.ok {
    border-left-color: #b4f078;
    background: rgba(180,240,120,0.05);
    color: #e3f3d3;
  }
  blockquote {
    border-left: 3px solid #ffb454;
    background: rgba(255,180,84,0.06);
    padding: 8px 14px;
    border-radius: 8px;
    color: #efe6d6;
    font-style: italic;
  }
  footer {
    color: #6e7681;
    font-size: 0.55em;
  }
  section.lead {
    text-align: center;
    justify-content: center;
    align-items: center;
  }
  section.lead > *,
  section.lead h1,
  section.lead h2,
  section.lead h3 {
    text-align: center;
  }
  section.lead h1 {
    font-size: 2.6em;
    border: none;
  }
  table {
    margin: 0;
  }
footer: 'Agents Under the Hood · 01-foundations'
---

<!-- _class: lead invert -->

<span class="eyebrow">live demo companion · 30–45 min</span>

# 🤖 Agents Under the Hood
## from *stateless LLM calls* → an *agentic loop*

<br>

Four steps. Real code. Built live.

<br>

<span class="chip">loop</span> <span class="chip">tools</span> <span class="chip">context</span>

---

# 👋 How I Got Here

I started exploring agents a while ago and decided to share what I was learning — *I should have started earlier.*

One of those posts —
**[How Agents Work: The Patterns Behind the Magic](https://agenticloopsai.substack.com/p/how-agents-work-the-patterns-behind)**
— caught <span class="accent">Yuriy's</span> eye, and here we are.

---

# 🤔 Why Understand the Internals?

AI is moving fast. Like any fast-growing technology, it's hard to separate **hype** from **substance**.

I look at it pragmatically:

> This technology isn't going anywhere.
> As engineers, we need to adapt and learn.

Understanding the patterns matters — just like any other technology.

---

# 🌐 Same Story as the Early Web

<div class="columns">
<div>

### <span class="accent">Mid-90s → Early 2000s</span>
The internet was new and confusing — then it changed everything.

Some engineers adapted: HTML → JS → frameworks. They realized the web didn't *replace* software engineering — it *became part of it*.

Others struggled.

</div>
<div>

### <span class="accent">AI Today</span>
It won't replace software engineering — it'll **become part of it**.

Engineers who understand how agents work will:
- 🏗️ build better systems
- 🐛 debug them more effectively
- 🎯 design for AI's strengths *and* limits

</div>
</div>

> Just as understanding **HTTP and statelessness** made you a better web developer — understanding **prompts, tools, memory, and failure modes** makes you a better engineer in an AI-augmented world.

---

<!-- _class: lead invert -->

# 🎯 The Goal

Not to become an **AI specialist**.

<br>

To be **fluent enough** that
when an agentic workflow is the right solution,
you recognize it —

<br>

and when it isn't,
**you recognize that too.**

---

# 🧠 First Principle — LLM Is a *Pure Function*

<span class="eyebrow">stateless · non-deterministic · token-bounded</span>

```python
response = llm(messages, tools, params)
```

- **No memory** between calls
- **You** keep the state, you replay it every turn
- Same input → *distribution* of outputs, not one answer

> Every "conversation" is the client stuffing history back into the prompt.

<span class="chip">stateless</span> <span class="chip">non-deterministic</span> <span class="chip">token-bounded</span>

---

# 🗺️ What We'll Build

```mermaid
flowchart LR
    A[📞 LLM Call] --> B[💬 Chat]
    B --> C[🔧 Tool Use]
    C --> D[🔁 Agent Loop]
```

| <span class="step-pill">1</span> | **LLM Call** | stateless request/response |
|:-:|---|---|
| <span class="step-pill">2</span> | **Chat** | conversation history |
| <span class="step-pill">3</span> | **Tool Use** | function calling |
| <span class="step-pill">4</span> | **Agent Loop** | autonomy + multi-step |

> Once you see the loop, you stop being a *consumer* and start being a *producer* of AI.

---

# <span class="step-pill">Step 1</span> Simple LLM Call

```mermaid
flowchart LR
    U([🗣️ Prompt]) -->|send| L[🧠 LLM]
    L -->|return| O([📄 Response])
```

<span class="eyebrow">one prompt in, one answer out · no memory · no tools</span>

---

# <span class="step-pill">Step 1</span> Pros & Cons

<div class="columns">
<div>

### <span class="pros">✅ Pros</span>
- Stateless & predictable
- Easy to cache
- Cheapest possible call
- Great for one-shot tasks

</div>
<div>

### <span class="cons">⚠️ Cons</span>
- No memory
- No actions
- No iteration
- No grounding in reality

</div>
</div>

---

# <span class="step-pill">Step 1</span> Code

```python
def ask(prompt: str) -> str:
    r = client.messages.create(
        model="claude-sonnet-4-6",
        messages=[{"role":"user","content":prompt}],
    )
    return r.content[0].text
```

<div class="callout">🎤 <strong>Say out loud:</strong> "Every LLM product on earth starts here. Everything we add next is scaffolding around this call."</div>

---

# <span class="step-pill">Step 2</span> Chat — History Is State

```mermaid
flowchart LR
    U([🗣️ User]) -->|append| H[(📝 History)]
    H -->|send| L[🧠 LLM]
    L -->|append| H
    L -->|reply| U
```

<span class="eyebrow">the client keeps the state · the LLM never remembers</span>

---

# <span class="step-pill">Step 2</span> Pros & Cons

<div class="columns">
<div>

### <span class="pros">✅ Pros</span>
- Natural multi-turn UX
- Context across messages
- Foundation for everything

</div>
<div>

### <span class="cons">⚠️ Cons</span>
- Context grows linearly → 💸
- Still **passive** — no actions
- Token bloat → drift

</div>
</div>

---

# <span class="step-pill">Step 2</span> Code

```python
history.append({"role":"user", "content": msg})

r = client.messages.create(messages=history)   # ← replay ALL of it

history.append({"role":"assistant", "content": r.content[0].text})
```

<div class="callout danger">⚠️ <strong>First failure mode:</strong> history grows unbounded → context window fills → older info drifts out. <em>Context pollution</em> incoming.</div>

---

# <span class="step-pill">Step 3</span> Tool Use — Give It Hands

```mermaid
flowchart LR
    L[🧠 LLM] -->|request| T[🔧 Tool]
    T -->|return| L
    L -->|respond| O([📄 Response])
```

<span class="eyebrow">the LLM doesn't call functions · it requests them · YOU run them</span>

---

# <span class="step-pill">Step 3</span> Pros & Cons

<div class="columns">
<div>

### <span class="pros">✅ Pros</span>
- LLM can **act** on the world
- Grounded in real data
- Structured I/O via JSON Schema

</div>
<div>

### <span class="cons">⚠️ Cons</span>
- Schemas eat tokens
- Selection errors at scale
- Needs **safety guardrails**

</div>
</div>

---

# <span class="step-pill">Step 3</span> Code

```python
tools = [{
  "name": "get_weather",
  "description": "Current weather for a city",
  "input_schema": {"type":"object",
    "properties": {"city": {"type":"string"}},
    "required": ["city"]}
}]

# LLM emits tool_use → YOUR code runs it → return tool_result
```

<div class="callout">💡 <strong>Key insight:</strong> the LLM does not <em>call</em> your function. It <em>requests</em> it. <strong>You are the runtime.</strong></div>

---

# <span class="step-pill">Step 4</span> Agent Loop — Autonomy

```mermaid
flowchart TD
    A([🗣️ Goal]) -->|send| B[🧠 LLM]
    B -->|evaluate| C{⚙️ Tool Calls?}
    C -->|yes| E[🔧 Tools]
    E -->|append| B
    C -->|no| D([📄 Response])
```

<span class="eyebrow">think → act → observe → repeat</span>

---

# <span class="step-pill">Step 4</span> Pros & Cons

<div class="columns">
<div>

### <span class="pros">✅ Pros</span>
- Solves multi-step tasks
- Self-corrects on failure
- Composes tools dynamically

</div>
<div>

### <span class="cons">⚠️ Cons</span>
- Unbounded cost / loops
- Hard to debug
- Context pollution grows fast

</div>
</div>

---

# <span class="step-pill">Step 4</span> Code

```python
for step in range(MAX_STEPS):
    r = client.messages.create(tools=tools, messages=messages)
    messages.append({"role":"assistant", "content": r.content})

    if r.stop_reason != "tool_use":
        break                                   # ← natural-language answer

    messages.append({"role":"user", "content": run_tools(r)})
```

<div class="callout ok">✨ <strong>That's the entire agent.</strong> Cursor, Claude Code, Copilot Agent — all variants of this loop with better tools, prompts, and guardrails.</div>

---

# 🧾 The 3 Truths Nobody Tells Consumers

<div class="columns">
<div>

### ① <span class="cons">Statelessness</span>
The LLM has no memory. Every "it remembered me" is code replaying history.

<span class="chip">you control it</span>

### ② <span class="cons">Non-determinism</span>
Same input → different outputs. Great for creativity, catastrophic for reliability.

<span class="chip warn">need evals, not unit tests</span>

</div>
<div>

### ③ <span class="cons">Context pollution</span>
Every tool result, retry, error gets appended. After 20 steps the agent is swimming in its own exhaust.

<span class="chip danger">summarize · compact · fork</span>

### ➕ Cost compounds
Turn N resends turns 1..N-1. Cost is ~O(N²) over a session.

<span class="chip warn">cap steps, cap tokens</span>

</div>
</div>

---

# 🌐 MCP — Model Context Protocol

```mermaid
flowchart LR
    A[🧠 Agent] <-->|invoke| S1[🔌 GitHub Server]
    A <-->|invoke| S2[🔌 Slack Server]
    A <-->|invoke| S3[🔌 Postgres Server]
```

> **"USB for agent tools"** — one plug shape, any device.

<div class="columns">
<div>

### <span class="pros">✅ Pros</span>
- Plug-and-play integrations
- Decouples agent ↔ tools
- Reusable across clients (Cursor, Claude Code, ChatGPT…)

</div>
<div>

### <span class="cons">⚠️ Trade-offs</span>
- **Schema tax** — every tool loaded on every call
- **Choice paralysis** — more tools → worse selection
- **Security surface** — each server reads creds
- **Name collisions** — two `search` tools → mispicks

</div>
</div>

<span class="chip">standard</span> <span class="chip">pluggable</span> <span class="chip danger">schema tax</span>

---

# 📦 Skills — Lazy-Loaded Playbooks

```mermaid
flowchart LR
    U["🗣️ make a pptx"] -->|match| R["📚 Skill Registry<br/>~100 tok"]
    R -->|load| S["📦 SKILL.md<br/>~2–5k tok"]
    S -->|inject| A["🧠 Agent Loop"]
```

**Anatomy:**

```
my-skill/
├── SKILL.md        # playbook + frontmatter (when to invoke)
├── scripts/helper.py
└── assets/template.docx
```

<div class="callout">💡 Unused skills <strong>never hit the context</strong> → ship 50 skills with ~zero baseline cost.</div>

<span class="chip ok">lazy-loaded</span> <span class="chip">prompt + code + assets</span> <span class="chip">convention > protocol</span>

---

# ⚔️ MCP vs Skills — When to Use Which

<div class="columns">
<div>

### 🔧 <span class="accent">MCP</span> fits when…
- You need **live data** (GitHub, Slack, DB)
- You need **real-world side-effects**
- Action = clean function signature
- Many agents need the same capability

</div>
<div>

### 📦 <span class="accent">Skills</span> fit when…
- Encoding **how to do something**
- Long process, conditional steps, examples
- Want a **catalog of 50+** without tool bloat
- Versioned know-how shipped with code

</div>
</div>

<div class="callout ok">🎯 <strong>They compose.</strong> A skill's playbook can instruct the agent to call MCP tools.</div>

<br>

### <span class="hand">MCP adds hands. Skills add instincts.</span>

---

# 🧹 Context Pollution — Reiteration

```mermaid
flowchart LR
    T1[🔧 Tools] -->|inflate| P[(📈 Context)]
    T2[🔌 MCP Servers] -->|inflate| P
    T3[💬 Chat History] -->|inflate| P
    P -->|degrade| L[🧠 LLM]
```

```python
prompt = (
    system_prompt         # ~500 tokens
    + tool_schemas        # ~6k × N servers
    + chat_history        # grows O(turns)
    + user_message        # tiny
)
```

> **Every token in context is a token the model must reason over.**
> Curate ruthlessly.

---

<!-- _class: lead invert -->

# 🎯 From Consumer to Producer

An agent isn't a new kind of intelligence.
It's a **control flow** —
`while` loop + tools + history — around a stateless function.

<br>

🧱 Start simple → add primitives only when needed
🔧 Tools give power — schemas cost tokens
🔁 The loop is ~30 lines of code
🌐 MCP adds hands · 📦 Skills add instincts
🧹 **Context is the new RAM — manage it**

<br>

### <span class="hand">Once you see the loop, you can build one tonight.</span>

`github.com/agenticloops-ai/agentic-ai-engineering`
