<!-- ---
title: "Streaming & Real-Time Output"
description: "Token-by-token streaming responses and handling tool calls mid-stream"
icon: "zap"
--- -->

# Streaming & Real-Time Output

Make agents feel alive with real-time, token-by-token responses. Every tutorial so far uses blocking API calls — the user waits in silence until the full response arrives. This tutorial adds streaming, transforming the experience from "did it freeze?" to "it's thinking and I can see it."

The real challenge isn't basic streaming — it's streaming with tool calls. When Claude decides to call a tool mid-response, you need to detect it, execute the tool, feed the result back, and resume streaming. This tutorial makes that approachable.

## 🎯 What You'll Learn

- Stream Claude responses token-by-token using `client.messages.stream()`
- Render streaming markdown in the terminal with Rich `Live` display
- Understand the full streaming event lifecycle (message_start → content_block_delta → message_stop)
- Handle tool_use blocks mid-stream — detect, execute, resume
- Build a complete streaming agent loop with tool calls
- Track token usage with streaming (usage arrives at stream end)

## 📦 Available Examples

| Provider                                           | File                                                                        | Description                            |
| -------------------------------------------------- | --------------------------------------------------------------------------- | -------------------------------------- |
| ![Anthropic](../../common/badges/anthropic.svg)    | [01_streaming_fundamentals.py](01_streaming_fundamentals.py)                | Text streaming + multi-turn chat       |
| ![Anthropic](../../common/badges/anthropic.svg)    | [02_streaming_agent.py](02_streaming_agent.py)                              | Streaming agent with tool calls        |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 03-advanced-techniques/02-streaming python {script_name}

# Start with fundamentals
uv run --directory 03-advanced-techniques/02-streaming python 01_streaming_fundamentals.py

# Then try the streaming agent
uv run --directory 03-advanced-techniques/02-streaming python 02_streaming_agent.py
```

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### 1. Two Ways to Stream

Anthropic provides two streaming approaches. Start with the simple one, graduate to events when you need control.

**Simple — `.text_stream` iterator:**

```python
with client.messages.stream(
    model="claude-sonnet-4-20250514",
    max_tokens=2048,
    messages=messages,
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)  # each chunk is a few characters
```

This is the easiest way to stream. The iterator yields plain text strings — just the content deltas. Perfect for simple use cases where you don't need event-level control.

**Event-based — full lifecycle control:**

```python
with client.messages.stream(...) as stream:
    for event in stream:
        if event.type == "content_block_start":
            # A new content block (text or tool_use) is starting
            pass
        elif event.type == "content_block_delta":
            if event.delta.type == "text_delta":
                print(event.delta.text, end="")
            elif event.delta.type == "input_json_delta":
                # Tool input parameters streaming in
                pass
        elif event.type == "content_block_stop":
            # Block finished
            pass
        elif event.type == "message_delta":
            # stop_reason is now available
            print(f"\nStop reason: {event.delta.stop_reason}")
```

Use event-based iteration when you need to detect tool calls, track block boundaries, or build custom rendering logic.

### 2. Streaming Event Lifecycle

Every stream follows this sequence:

```
message_start                          ← stream begins
│
├─ content_block_start (index=0)       ← first block (usually text)
│  ├─ content_block_delta              ← text chunks arrive
│  ├─ content_block_delta              ← more text
│  └─ content_block_stop              ← block complete
│
├─ content_block_start (index=1)       ← could be another text or tool_use block
│  ├─ content_block_delta              ← text or input_json deltas
│  └─ content_block_stop
│
├─ message_delta                       ← stop_reason + final usage stats
└─ message_stop                        ← stream is done
```

The key insight: a single response can contain **multiple content blocks** — both text and tool_use blocks interleaved. This is what makes streaming with tools interesting.

### 3. Streaming with Tool Calls

When Claude wants to call a tool, the stream contains a `tool_use` content block. The flow becomes:

```
User: "What's the weather in Tokyo?"
        │
        ▼
  ┌─ Stream starts ──────────────────────────┐
  │ text block: "Let me check the weather..."  │  ← streamed to terminal
  │ tool_use block: get_weather(city="Tokyo")  │  ← detected mid-stream
  │ stop_reason: "tool_use"                    │
  └────────────────────────────────────────────┘
        │
        ▼ execute tool
  ┌─ Tool result ────────────────────┐
  │ {"city": "Tokyo", "temp_f": 58}  │
  └──────────────────────────────────┘
        │
        ▼ feed result back, start new stream
  ┌─ Stream resumes ─────────────────────────────────┐
  │ text block: "It's 58°F and clear in Tokyo today." │  ← streamed to terminal
  │ stop_reason: "end_turn"                            │
  └────────────────────────────────────────────────────┘
```

The agent loop checks `stop_reason` after each stream:
- `"end_turn"` → done, return the response
- `"tool_use"` → execute tools, feed results back, stream again
- `"max_tokens"` → response was truncated

### 4. Rendering with Rich Live Display

Raw `print()` gives you streaming text, but it can't handle markdown formatting mid-stream. Rich's `Live` display solves this — it re-renders the full accumulated markdown on every update:

```python
from rich.live import Live
from rich.markdown import Markdown

accumulated = ""
with Live(Markdown(""), refresh_per_second=15, console=console) as live:
    for text in stream.text_stream:
        accumulated += text
        live.update(Markdown(accumulated))
```

The `refresh_per_second=15` parameter throttles updates to keep rendering smooth. The user sees formatted markdown building up in real-time — headers, bullet points, bold text all render correctly as they stream in.

### 5. Token Tracking with Streaming

Token usage isn't available until the stream completes. Use `get_final_message()` to retrieve it:

```python
with client.messages.stream(...) as stream:
    for text in stream.text_stream:
        print(text, end="")

    # Usage is available after stream completes
    final_message = stream.get_final_message()
    token_tracker.track(final_message.usage)
    print(f"\nTokens: {final_message.usage.input_tokens} in, {final_message.usage.output_tokens} out")
```

`get_final_message()` returns the fully accumulated `Message` object — same as what `client.messages.create()` would return, but you got to stream it first.

## 🏗️ Code Structure

### Script 01 — Streaming Fundamentals

```python
class StreamingChat:
    """Interactive chat with streaming responses."""

    def stream_simple(self, user_input, console) -> str:
        """Stream using .text_stream — the easy way."""
        with client.messages.stream(...) as stream:
            for text in stream.text_stream:   # just text strings
                # render with Rich Live
            final = stream.get_final_message()
            # track tokens

    def stream_with_events(self, user_input, console) -> str:
        """Stream with event-based iteration — full control."""
        with client.messages.stream(...) as stream:
            for event in stream:              # typed event objects
                if event.type == "content_block_delta":
                    # handle text_delta, input_json_delta
```

### Script 02 — Streaming Agent

```python
class StreamingAgent:
    """Streaming agent with tool call handling."""

    def run(self, user_input, console) -> str:
        """Agent loop: stream → detect tools → execute → resume."""
        while True:
            response = self._stream_response(console)
            if response.stop_reason == "tool_use":
                results = self._execute_tool_calls(response.content, console)
                # feed results back, loop again
            else:
                return extract_text(response)   # done

    def _stream_response(self, console) -> Message:
        """Stream one API call, rendering text + tool indicators."""
        with client.messages.stream(tools=TOOLS, ...) as stream:
            self._render_mixed_stream(stream, console)
            return stream.get_final_message()

    def _render_mixed_stream(self, stream, console) -> None:
        """The key method: handle interleaved text and tool_use blocks."""
        for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "text":
                    # start Rich Live display
                elif event.content_block.type == "tool_use":
                    # show "Calling tool_name..."
            elif event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    # update live markdown display
```

## ⚠️ Important Considerations

- **Streaming doesn't reduce total latency** — same tokens, same processing time. It reduces *perceived* latency by showing progress immediately.
- **Error handling** — streams can fail mid-way. Always wrap in try/except and handle `APIError`. The `Live` display must be stopped in a `finally` block to avoid terminal corruption.
- **`stop_reason` is critical** — always check it. `"tool_use"` means execute tools and continue. `"end_turn"` means done. `"max_tokens"` means the response was truncated.
- **Token tracking timing** — usage stats arrive only after the stream completes via `get_final_message()`. You cannot track tokens mid-stream.
- **Conversation history** — after streaming, you need the full response content for message history. Use `get_final_message().content` to get the complete list of content blocks.

## 👉 Next Steps

Once you've mastered streaming, continue to:
- **[Context Engineering](../03-context-engineering/)** — Manage finite context windows with sliding windows and summarization
- **Experiment** — Add more tools to the streaming agent and try prompts that trigger multiple tool calls in one response
- **Explore** — Try switching between `stream.text_stream` and event iteration to see the difference in control vs simplicity
