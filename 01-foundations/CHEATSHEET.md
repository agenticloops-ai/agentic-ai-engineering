<!-- ---
title: "Agent Building Cheat Sheet"
description: "Quick reference for building AI agents — from first API call to autonomous systems"
--- -->

# How to Build an Agent — Cheat Sheet

A quick reference card covering every pattern you need to build AI agents, from a single LLM call to autonomous, tool-using systems. Based on [Foundations of AI Agents](./README.md) tutorials and the [How Agents Work: The Patterns Behind the Magic](https://agenticloopsai.substack.com/p/how-agents-work-the-patterns-behind) article.

---

## The Progression

```
LLM Call → Prompt Engineering → Chat → Tool Use → Agent Loop → Augmented LLM
   1️⃣           2️⃣              3️⃣       4️⃣          5️⃣            🏆
```

Each step adds one capability. Together they form a complete agent.

---

## 1️⃣ LLM Call — The Foundation

> One prompt in, one response out. Everything starts here.

```python
class LLMClient:
    def __init__(self, model: str):
        self.client = anthropic.Anthropic()
        self.model = model

    def run(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system="You are a helpful AI assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
```

**Key points:**
- Single-shot — no memory, no tools, no loop
- Always track tokens via `response.usage`
- Encapsulate LLM logic in a class, orchestration in `main()`

> [Full example →](01-simple-llm-call/01_llm_call_anthropic.py)

---

## 2️⃣ Prompt Engineering — Controlling Behavior

> The loop is the skeleton. The prompt encodes behavior.

### System Prompts (3 levels)

| Level | System Prompt | Output Quality |
|-------|--------------|----------------|
| Generic | `"You are a helpful assistant"` | Vague, hedging |
| Role | `"You are a senior support engineer..."` | Decisive, expert |
| Role + Format | Role + constraints + output sections | Terse, actionable |

### Techniques

| Technique | When to Use | Example |
|-----------|------------|---------|
| **System prompt** | Always — sets persona & constraints | `"You are a senior engineer. Be concise."` |
| **Few-shot** | Domain-specific labels or formats | Provide 3-5 input/output examples |
| **Chain-of-thought** | Complex reasoning tasks | `"Analyze step by step: 1. What patterns... 2. What clues..."` |
| **Structured output** | When you need parseable JSON | Native schema (best) or prompt-based (fallback) |

**Key points:**
- Low temperature (0.1) for consistency
- Few-shot adds input tokens but improves accuracy
- Native schema enforcement > prompt-based JSON extraction

> [Full examples →](02-prompt-engineering/)

---

## 3️⃣ Chat — Conversation History

> Without history, every message is a stranger. With it, the model remembers.

```python
class ChatSession:
    def __init__(self, model: str):
        self.client = anthropic.Anthropic()
        self.messages: list[dict[str, str]] = []

    def send_message(self, user_message: str) -> str:
        self.messages.append({"role": "user", "content": user_message})

        response = self.client.messages.create(
            model=self.model,
            messages=self.messages,        # ← full history every call
        )

        assistant_text = response.content[0].text
        self.messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text
```

**Key points:**
- Full history sent each call — costs grow with conversation length
- Alternating `user` / `assistant` roles
- Production systems add: sliding windows, summarization, context management

> [Full example →](03-chat/01_chat_anthropic.py)

---

## 4️⃣ Tool Use — Giving the LLM Hands

> Without tools, the model writes code it's never run. Tools give it the ability to interact with the outside world.

### Define Tools (JSON Schema)

```python
TOOLS = [{
    "name": "bash",
    "description": "Run a bash command",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command"},
        },
        "required": ["command"],
    },
}]
```

### Execute Tools (Dispatcher Pattern)

```python
TOOL_FUNCTIONS = {"calculator": calculator, "read_file": read_file, "bash": run_bash}

def execute_tool(name: str, tool_input: dict) -> Any:
    return TOOL_FUNCTIONS[name](**tool_input)
```

### Handle the Tool Call Loop

```python
response = client.messages.create(model=model, tools=TOOLS, messages=messages)

if response.stop_reason == "tool_use":
    for block in response.content:
        if isinstance(block, ToolUseBlock):
            result = execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": tool_results})
```

### Safety Guardrails

```python
BLOCKED_COMMANDS = ["rm", "sudo", "chmod", "shutdown", ">", ">>"]

def run_bash(command: str) -> dict:
    for blocked in BLOCKED_COMMANDS:
        if blocked in command.lower():
            return {"error": f"Blocked: contains '{blocked}'"}
    # ... execute safely ...
```

**Key points:**
- `stop_reason == "tool_use"` → model wants to call a tool
- Always validate tool inputs, block dangerous commands
- Multiple tool calls can happen in a single response

> [Full example →](04-tool-use/01_tool_use_anthropic.py)

---

## 5️⃣ Agent Loop — Autonomy

> The core pattern: **Reason → Act → Observe → Repeat.** This is what turns an LLM into a software engineer.

### The Minimal Agent (55 lines)

```python
def agent(goal: str) -> str:
    messages = [{"role": "user", "content": goal}]

    for _ in range(10):                     # max iterations — prevent infinite loops
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=messages,
            tools=TOOLS,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":  # ← task complete
            return response.content[0].text

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":         # ← needs a tool
                result = subprocess.run(block.input["command"], ...)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result.stdout or result.stderr,
                })
        messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached"
```

### The Agent Loop Visualized

```
┌──────────────────────────────┐
│         User Task            │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│   Call LLM with tools        │◄──────────────┐
└──────────────┬───────────────┘               │
               ▼                               │
        ┌─────────────┐                        │
        │ Tool calls?  │                       │
        └──────┬──────┘                        │
          NO   │   YES                         │
          ▼    │    ▼                           │
    ┌─────────┐│┌──────────────────────┐       │
    │ Return  │││ Execute tools        │       │
    │ response│││ Append results       │───────┘
    └─────────┘│└──────────────────────┘
               │
```

**Key points:**
- Max iterations prevent runaway loops (typically 10)
- `stop_reason: "end_turn"` = done, `"tool_use"` = keep going
- Each iteration: LLM sees **full history** including all prior tool results
- The agent drives the conversation — no human input needed per step

> [Minimal agent →](05-agent-loop/01_minimal_agent.py) · [Full coding agent →](05-agent-loop/02_coding_agent_anthropic.py)

---

## 🏆 Augmented LLM — The Complete Pattern

> The building block of all agentic systems: an LLM enhanced with **retrieval**, **tools**, and **memory**.

```
┌─────────────────────────────────────────────────┐
│                 Augmented LLM                    │
│                                                  │
│   ┌───────────┐  ┌────────┐  ┌────────────┐    │
│   │ Retrieval │  │ Tools  │  │  Memory    │    │
│   │ (RAG)     │  │        │  │            │    │
│   └─────┬─────┘  └───┬────┘  └─────┬──────┘    │
│         │            │             │            │
│         └────────────┼─────────────┘            │
│                      ▼                          │
│               ┌────────────┐                    │
│               │    LLM     │                    │
│               └────────────┘                    │
└─────────────────────────────────────────────────┘
```

| Component | What It Does | Example |
|-----------|-------------|---------|
| **Retrieval** | Fetches relevant context before the LLM responds | Semantic code search via ChromaDB embeddings |
| **Tools** | Lets the LLM take actions in the world | `read_file`, `bash`, `grep`, `search_code` |
| **Memory** | Persists knowledge across sessions | JSON store loaded into system prompt |

> [Codebase Navigator →](06-codebase-navigator/01_codebase_navigator.py)

---

## ReAct Pattern — Think, Act, Observe

> ReAct is reactive — it figures things out step by step. Act, observe, adjust.

The ReAct pattern (Reason + Act) interleaves reasoning with action. The LLM explicitly thinks about what to do, takes an action, observes the result, then decides the next step.

```
┌────────────┐     ┌────────────┐     ┌────────────┐
│  Thought   │────▶│   Action   │────▶│ Observation│
│ "I need to │     │ search for │     │ Found 3    │
│  find..."  │     │ the file   │     │ matches    │
└────────────┘     └────────────┘     └─────┬──────┘
      ▲                                      │
      └──────────────────────────────────────┘
                    repeat until done
```

**When to use:** Exploratory tasks where you don't know the steps upfront — debugging, research, investigation.

**This is what Tutorial 05 implements.** The agent loop _is_ ReAct: the LLM reasons (via its response), acts (via tool calls), observes (via tool results), and repeats.

---

## Planning Pattern — Design Then Execute

> For complex tasks, plan first. Break work into steps, then execute each one.

The Planning Pattern adds a deliberate planning phase before execution. The LLM creates a structured plan, then works through each step using ReAct loops.

```
┌──────────────────────────────────────────────────────────┐
│                    Planning Pattern                       │
│                                                          │
│  ┌──────────┐    ┌──────────────────────────────────┐   │
│  │  Plan    │    │  Execute (ReAct per step)        │   │
│  │          │    │                                    │   │
│  │ Step 1   │───▶│  Reason → Act → Observe → ...    │   │
│  │ Step 2   │───▶│  Reason → Act → Observe → ...    │   │
│  │ Step 3   │───▶│  Reason → Act → Observe → ...    │   │
│  └──────────┘    └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

**When to use:** Multi-file refactors, feature implementations, migrations — tasks where you know the shape of the work upfront.

**Key difference:** ReAct is bottom-up (explore then decide). Planning is top-down (decide then execute). Both use the same agent loop underneath.

---

## Choosing the Right Pattern

| Pattern | Best For | Approach | Complexity |
|---------|----------|----------|------------|
| **Single LLM Call** | One-shot questions, classification | Prompt → Response | Lowest |
| **Chat** | Conversations, iterative refinement | History + Loop | Low |
| **Tool Use** | Tasks needing external data/actions | Call → Execute → Return | Medium |
| **ReAct (Agent Loop)** | Exploratory, unknown steps | Reason → Act → Observe → Repeat | Medium-High |
| **Planning** | Complex, multi-step known structure | Plan → Execute steps via ReAct | High |
| **Augmented LLM** | Production systems needing RAG + memory | Retrieval + Tools + Memory + Loop | Highest |

> These aren't stages — they're tools in your toolkit. Pick the right one for your task.

---

## Production Considerations

When moving from tutorials to production, add:

- **Context management** — sliding windows, summarization (history grows fast)
- **Rate limiting** — respect API limits, add backoff
- **Cost control** — set token budgets, track spend per task
- **Tool sandboxing** — run untrusted commands in containers
- **Guardrails** — block dangerous operations, validate all inputs
- **Observability** — log every LLM call, tool execution, and decision
- **Max iterations** — always cap the loop to prevent runaway agents
- **Error recovery** — tools fail; the agent should retry or try alternatives

---

## Quick Reference

```python
# The entire agent pattern in 6 lines of pseudocode:

messages = [user_task]
while not done:
    response = llm(messages, tools)       # Reason
    if response.done: return response     # Check
    results = execute(response.tools)     # Act
    messages += [response, results]       # Observe → Loop
```

**That's it.** An LLM API, some tools, and a loop. No framework required.

---

## Resources

- [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- [How Agents Work: The Patterns Behind the Magic](https://agenticloopsai.substack.com/p/how-agents-work-the-patterns-behind) — AgenticLoops AI
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) — Yao et al. 2022
- [Anthropic Tool Use Guide](https://docs.anthropic.com/en/docs/tool-use)
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
