---
title: "Foundations of AI Agents"
description: "Master the core building blocks of AI agents through progressive, hands-on tutorials"
---

# Foundations of AI Agents

Master the core building blocks of AI agents through progressive, hands-on tutorials.

<!-- TODO: Add reference to blog post "How Agents Work: The Patterns Behind the Magic" on Substack -->

## 🗺️ Progression Path

Each tutorial builds on the previous one:

```
Simple LLM Call
    ↓
  (adds behavior control)
    ↓
Prompt Engineering
    ↓
  (adds conversation history)
    ↓
Interactive Chat
    ↓
  (adds function calling)
    ↓
Tool Use
    ↓
  (adds autonomy)
    ↓
Agent Loop
```

## 💡 Tips for Success

1. **Run each tutorial** - Don't just read the code, execute it
2. **Try both versions** - Compare Anthropic and OpenAI approaches
3. **Modify and experiment** - Change prompts, add features, break things
4. **Read the logs** - Understand what's happening at each step
5. **Track tokens** - Be aware of API usage and costs
6. **Build progressively** - Each tutorial introduces one new concept

> Each tutorial includes **both Anthropic and OpenAI implementations** in the same directory for easy comparison!

## 📚 Tutorials

### [01 - Simple LLM Call](01-simple-llm-call/)

**What you'll learn:**
- Initialize API client
- Make your first API calls
- Understand both streaming and non-streaming APIs
- Track token usage with callbacks

**Key concepts:** API basics, token tracking, clean code patterns

---

### [02 - Prompt Engineering](02-prompt-engineering/)

**What you'll learn:**
- Craft effective system messages
- Use role-based prompting
- Apply few-shot learning
- Request structured output (JSON)

**Evolution:** Adds control over model behavior and output format

---

### [03 - Chat](03-chat/)

**What you'll learn:**
- Build interactive chat loops
- Manage conversation history
- Handle message roles (user/assistant)
- Create better user experiences with Rich formatting


**Evolution:** Adds conversation context and interactivity to previous tutorials

---

### [04 - Tool Use](04-tool-use/)

**What you'll learn:**
- Define tools with proper schemas
- Handle tool calling requests
- Execute tools and return results
- Manage multi-turn tool interactions

**Evolution:** Enables the model to take actions via function calling

---

### [05 - Agent Loop](05-agent-loop/)

**What you'll learn:**
- Build a complete autonomous agent loop
- Implement decision-making logic
- Handle complex multi-step tasks
- Detect task completion automatically

**Evolution:** Combines everything into a fully autonomous agent that chains tool calls

---

## 🔗 Resources

### Anthropic Claude
- [Anthropic Documentation](https://docs.anthropic.com/)
- [Claude API Reference](https://docs.anthropic.com/en/api/messages)
- [Tool Use Guide](https://docs.anthropic.com/en/docs/tool-use)
- [Prompt Engineering Guide](https://docs.anthropic.com/en/docs/prompt-engineering)

### OpenAI GPT
- [OpenAI Documentation](https://platform.openai.com/docs)
- [Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering)
