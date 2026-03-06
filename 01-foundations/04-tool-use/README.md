<!-- ---
title: "Tool Use"
description: "Enable LLMs to call functions and interact with external systems"
icon: "wrench"
--- -->

# Tool Use

Learn how to give LLMs the ability to call functions (tools) to interact with the real world. This tutorial demonstrates how to define tools, handle tool calls, and execute functions on behalf of the model.

## 🎯 What You'll Learn

- Define tools with JSON Schema for LLM consumption
- Handle the tool call loop (request -> execute -> respond)
- Execute functions safely with guardrails
- Work with multiple tool calls in a single response

## 📦 Available Examples

| Provider                                        | File                                                 | Description                        |
| ----------------------------------------------- | ---------------------------------------------------- | ---------------------------------- |
| ![Anthropic](../../common/badges/anthropic.svg) | [01_tool_use_anthropic.py](01_tool_use_anthropic.py) | Tool use with Claude Messages API  |
| ![OpenAI](../../common/badges/openai.svg)       | [02_tool_use_openai.py](02_tool_use_openai.py)       | Tool use with OpenAI Responses API |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
uv run --directory 01-foundations/04-tool-use python {script_name}

# Example
uv run --directory 01-foundations/04-tool-use python 01_tool_use_anthropic.py
```

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### 1. Tool Definition

Tools are defined using JSON Schema so the LLM understands what functions are available:

**Anthropic:**
```python
TOOLS = [
    {
        "name": "calculator",
        "description": "Performs basic arithmetic operations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide"],
                },
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["operation", "a", "b"],
        },
    },
]
```

**OpenAI:**
```python
TOOLS = [
    {
        "type": "function",
        "name": "calculator",
        "description": "Performs basic arithmetic operations.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide"],
                },
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["operation", "a", "b"],
        },
    },
]
```

### 2. The Tool Call Loop

The LLM doesn't execute tools directly - it requests tool calls that you execute:

```
User Message
    |
LLM Response (with tool_use)
    |
Execute Tool -> Get Result
    |
Send Result Back to LLM
    |
LLM Response (final answer)
```

**Anthropic:**
```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    tools=TOOLS,
    messages=messages,
)

if response.stop_reason == "tool_use":
    for block in response.content:
        if isinstance(block, ToolUseBlock):
            result = execute_tool(block.name, block.input)
            # Send result back with tool_use_id
```

**OpenAI:**
```python
response = client.responses.create(
    model="gpt-4.1",
    tools=TOOLS,
    input=messages,
)

for output in response.output:
    if output.type == "function_call":
        result = execute_tool(output.name, json.loads(output.arguments))
        # Send result back with call_id
```

### 3. Tool Implementation with Guardrails

Always validate and sanitize tool inputs, especially for system-level tools:

```python
BLOCKED_COMMANDS = ["rm", "sudo", "chmod", "shutdown", ">", ">>"]

def run_bash(command: str, timeout: int = 30) -> dict:
    """Execute a bash command with safety guardrails."""
    # Block dangerous commands
    for blocked in BLOCKED_COMMANDS:
        if blocked in command.lower():
            return {"error": f"Command blocked: contains '{blocked}'"}

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        timeout=timeout,
    )
    return {"stdout": result.stdout, "stderr": result.stderr}
```

### 4. Handling Multiple Tool Calls

LLMs can request multiple tool calls in a single response. Process all of them before continuing:

**Anthropic:**
```python
tool_results = []
for tool_use in tool_uses:
    result = execute_tool(tool_use.name, tool_use.input)
    tool_results.append({
        "type": "tool_result",
        "tool_use_id": tool_use.id,
        "content": json.dumps(result),
    })
messages.append({"role": "user", "content": tool_results})
```

**OpenAI:**
```python
# Add function calls to messages first
messages.extend(response.output)

# Then add results
for func_call in function_calls:
    result = execute_tool(func_call.name, json.loads(func_call.arguments))
    messages.append({
        "type": "function_call_output",
        "call_id": func_call.call_id,
        "output": json.dumps(result),
    })
```

## 🧰 Tools in This Tutorial

| Tool         | Description                                        |
| ------------ | -------------------------------------------------- |
| `calculator` | Basic arithmetic (add, subtract, multiply, divide) |
| `read_file`  | Read file contents from the filesystem             |
| `run_bash`   | Execute shell commands (with safety guardrails)    |

## 🏗️ Code Structure

Both examples follow a consistent structure:

```python
# 1. Define tools as JSON Schema
TOOLS = [...]

# 2. Implement tool functions
def calculator(operation: str, a: float, b: float) -> dict:
    ...

def read_file(path: str) -> dict:
    ...

def run_bash(command: str) -> dict:
    ...

# 3. Tool execution dispatcher
TOOL_FUNCTIONS = {"calculator": calculator, "read_file": read_file, ...}

def execute_tool(name: str, input: dict) -> Any:
    return TOOL_FUNCTIONS[name](**input)


# 4. Chat class with tool loop
class ToolUseChat:
    def send_message(self, message: str) -> str:
        while True:
            response = self.client.create(tools=TOOLS, ...)

            if has_tool_calls(response):
                execute_tools_and_add_results()
                continue
            else:
                return response.text


# 5. Main orchestration
def main():
    chat = ToolUseChat(model, token_tracker, console)
    while True:
        user_input = input()
        response = chat.send_message(user_input)
        print(response)
```

## 👉 Next Steps

Once you've mastered tool use, continue to:
- **[Agent Loop](../05-agent-loop/README.md)** - Build autonomous agents that use tools to complete tasks
- **Experiment** - Add more tools like web search, database queries, or API calls
- **Explore** - Implement tool choice modes (`auto`, `required`, `none`)
