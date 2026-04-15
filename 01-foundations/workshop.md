---
marp: true
theme: uncover
class: invert
paginate: true
backgroundColor: #0d1117
color: #e6edf3
style: |
  section {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    color: #e6edf3;
    padding: 50px;
    font-size: 24px;
  }
  h1 {
    color: #58a6ff;
    font-weight: 700;
    border-bottom: 2px solid #30363d;
    padding-bottom: 10px;
  }
  h2 {
    color: #79c0ff;
    font-weight: 600;
  }
  h3 {
    color: #d2a8ff;
  }
  code {
    background: #161b22;
    color: #ff7b72;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.85em;
  }
  pre {
    background: #161b22 !important;
    border: 1px solid #30363d;
    border-radius: 8px;
    font-size: 0.7em;
  }
  pre code {
    background: transparent;
    color: #e6edf3;
  }
  table {
    border-collapse: collapse;
    margin: 0 auto;
    font-size: 0.85em;
  }
  th {
    background: #21262d;
    color: #58a6ff;
    padding: 8px 14px;
    border: 1px solid #30363d;
  }
  td {
    padding: 8px 14px;
    border: 1px solid #30363d;
  }
  .columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.2rem;
  }
  .pros { color: #7ee787; }
  .cons { color: #ff7b72; }
  .accent { color: #d2a8ff; }
  blockquote {
    border-left: 4px solid #58a6ff;
    padding-left: 1rem;
    color: #8b949e;
    font-style: italic;
  }
  footer {
    color: #6e7681;
    font-size: 0.6em;
  }
  section.lead h1 {
    font-size: 2.4em;
    border: none;
    text-align: center;
  }
  section.lead {
    text-align: center;
  }
footer: 'How Agents Work · Under the Hood'
---

<!-- _class: lead invert -->

# 🤖 How Agents Work
## Building Agents from Scratch — Under the Hood

From a single LLM call → an autonomous agent loop

<br>

`workshop · 01-foundations`

---

# 🗺️ The Progression

```mermaid
flowchart LR
    A[📞 LLM Call] --> B[💬 Chat]
    B --> C[🔧 Tool Use]
    C --> D[🔁 Agent Loop]
    D --> E[🌐 MCP & Skills]
```

| # | Pattern | Adds |
|:-:|---------|------|
| 1 | **Simple LLM Call** | Stateless request/response |
| 2 | **Chat** | Conversation history |
| 3 | **Tool Use** | Function calling |
| 4 | **Agent Loop** | Autonomy + multi-step reasoning |
| ➕ | **MCP / Skills** | Scalable context engineering |

> Every "agent" is a composition of these primitives.

---

# 1️⃣ Simple LLM Call

```mermaid
flowchart LR
    U([🗣️ Prompt]) -->|request| L[🧠 LLM]
    L -->|response| O([📄 Text])
```

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

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": prompt}],
)
return response.content[0].text
```

---

# 2️⃣ Chat — Add Memory

```mermaid
flowchart LR
    U([🗣️ User]) -->|append| H[(📝 History)]
    H -->|messages| L[🧠 LLM]
    L -->|response| H
    L -->|reply| U
```

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
- Token bloat → drift & latency

</div>
</div>

```python
self.messages.append({"role": "user", "content": user_message})
response = self.client.messages.create(
    model=self.model, messages=self.messages,
)
self.messages.append({"role": "assistant", "content": response.content[0].text})
```

---

# 3️⃣ Tool Use — Add Actions

```mermaid
flowchart LR
    L[🧠 LLM] -->|tool_use| T[🔧 Tool]
    T -->|tool_result| L
    L -->|text| O([📄 Answer])
```

<div class="columns">
<div>

### <span class="pros">✅ Pros</span>
- LLM can **act** on the world
- Grounded answers (real data)
- Structured I/O via JSON Schema

</div>
<div>

### <span class="cons">⚠️ Cons</span>
- Tool schemas eat tokens
- Selection errors at scale
- Needs **safety guardrails**

</div>
</div>

```python
TOOLS = [{"name": "calculator", "input_schema": {...}}]
response = client.messages.create(model=model, tools=TOOLS, messages=messages)
for block in response.content:
    if isinstance(block, ToolUseBlock):
        result = execute_tool(block.name, block.input)
```

---

# 4️⃣ Agent Loop — Add Autonomy

```mermaid
flowchart TD
    A([🗣️ Goal]) --> B[🧠 LLM]
    B -->|tool_use?| C{⚙️ Decide}
    C -->|yes| E[🔧 Execute]
    E -->|append| B
    C -->|end_turn| D([📄 Done])
```

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
- **Context pollution** grows fast

</div>
</div>

```python
while iteration < max_iterations:
    response = client.messages.create(model=model, tools=TOOLS, messages=messages)
    if response.stop_reason == "end_turn":
        return response.content[0].text
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": run_tools(response)})
```

---

# 🌐 MCP — Model Context Protocol

```mermaid
flowchart LR
    A[🧠 Agent] <-->|MCP| S1[🔌 GitHub Server]
    A <-->|MCP| S2[🔌 DB Server]
    A <-->|MCP| S3[🔌 Filesystem]
```

> **"USB-C for LLM tools"** — one protocol, many integrations.

<div class="columns">
<div>

### <span class="pros">✅ Pros</span>
- Plug-and-play tool ecosystems
- Decouples agent ↔ tools
- Reusable across clients

</div>
<div>

### <span class="cons">⚠️ Cons</span>
- **Every MCP loads its full tool list** into context
- 5 servers → 100+ tools → 🤯
- Selection accuracy ↓ as N tools ↑
- Auth, sandboxing, trust boundaries

</div>
</div>

```python
# Connect once → tools auto-injected into every LLM call
client.add_mcp_server("github")  # +20 tools, +4k tokens... per turn
```

---

# 📦 Skills — Progressive Disclosure

```mermaid
flowchart LR
    A[🧠 Agent] -->|needs PDFs| L[📚 Skill Index]
    L -->|load on demand| S[📦 PDF Skill]
    S -->|instructions + scripts| A
```

> Skills = **lazy-loaded capability bundles** (instructions + code + resources).

<div class="columns">
<div>

### <span class="pros">✅ Pros</span>
- Loaded **only when relevant**
- Keeps base context lean
- Versioned, shareable, composable

</div>
<div>

### <span class="cons">⚠️ Cons</span>
- Discovery overhead
- Skill quality = agent quality
- Still trades context for capability

</div>
</div>

---

# ⚠️ The Context Pollution Problem

```mermaid
flowchart LR
    T1[🔧 +10 tools] --> P[(📈 Prompt)]
    T2[🔧 +20 MCP tools] --> P
    T3[💬 long history] --> P
    P -->|drift / cost / latency| L[🧠 LLM]
```

| Scaling Lever | Cost in Context | Symptom |
|---------------|-----------------|---------|
| More tools | Schemas in every call | Wrong tool selected |
| More MCP servers | Full toolset always loaded | Token bloat, latency |
| Longer history | O(n) growth | Forgetfulness, drift |
| More skills (eager) | Instructions duplicated | Confused priorities |

> **Rule of thumb:** every token in context is a token the model must reason over. Curate ruthlessly.

---

<!-- _class: lead invert -->

# 🎯 Takeaways

**Agents = LLM + Loop + Tools + Context Engineering**

🧱 Start simple → add primitives only when needed
🔧 Tools give power — schemas cost tokens
🔁 The loop is ~30 lines of code
🌐 MCP scales integrations, not context
📦 Skills load capabilities on demand
🧹 **Context is the new RAM — manage it**

<br>

### 🚀 Build one. Break it. Then scale it.

`github.com/agenticloops-ai/agentic-ai-engineering`
