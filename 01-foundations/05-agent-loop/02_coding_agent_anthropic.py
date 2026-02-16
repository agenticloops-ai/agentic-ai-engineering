"""
Agent Loop (Anthropic)

Demonstrates a minimal autonomous agent that:
- Takes a task from the user
- Decides which tools to use
- Executes tools in a loop until complete
"""

import json
import subprocess
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import TextBlock, ToolUseBlock
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import AnthropicTokenTracker

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

SYSTEM_PROMPT = """You are a coding agent. Use the provided tools to complete tasks.

Guidelines:
- Read files before modifying them
- Make changes incrementally and verify each step
- If a command fails, analyze the error and try a different approach
- When done, provide a brief summary of what you accomplished"""


# Tool definitions
TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a bash command and return its output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                }
            },
            "required": ["command"],
        },
    },
]


def execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool and return the result as a string."""
    if name == "read_file":
        try:
            return Path(tool_input["path"]).read_text()
        except Exception as e:
            return f"Error: {e}"

    elif name == "write_file":
        try:
            Path(tool_input["path"]).write_text(tool_input["content"])
            return f"Successfully wrote to {tool_input['path']}"
        except Exception as e:
            return f"Error: {e}"

    elif name == "bash":
        try:
            result = subprocess.run(
                tool_input["command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout + result.stderr
            return output if output else "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {e}"

    return f"Unknown tool: {name}"


class CodingAgent:
    """
    Minimal autonomous coding agent.

    Executes tools in a loop until the task is complete.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = AnthropicTokenTracker()

    def run(self, task: str) -> str:
        """Execute the agent loop for the given task."""
        logger.info(f"Task: {task}")

        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

        for iteration in range(self.max_iterations):
            logger.info(f"--- Iteration {iteration + 1} ---")

            # Call the model
            response = self.client.messages.create(
                model=self.model,
                temperature=0.1,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            self.token_tracker.track(response.usage)

            # Process response content
            assistant_content = []
            for block in response.content:
                if isinstance(block, TextBlock):
                    logger.info(f"🤖 Agent: {block.text}")
                    assistant_content.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    logger.info(f"🔧 Tool: {block.name}({json.dumps(block.input)})")
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )

            messages.append({"role": "assistant", "content": assistant_content})

            # If no tool use, task is complete
            if response.stop_reason == "end_turn":
                return response.content[0].text if response.content else "Done"

            # Execute tools and collect results
            tool_results = []
            for block in response.content:
                if isinstance(block, ToolUseBlock):
                    result = execute_tool(block.name, block.input)
                    logger.info(f"📋 Result: {result[:100]}{'...' if len(result) > 100 else ''}")
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

        return "Max iterations reached"


def main() -> None:
    """Main orchestration function."""
    console = Console()
    console.print(
        Panel(
            "Examples:\n"
            "  - Create a calculator following the style of existing files\n"
            "  - List current dependencies\n"
            "  - Explain code in the current folder\n\n"
            "Type 'quit' to exit.",
            title="Coding Agent (Anthropic)",
        )
    )

    agent = CodingAgent()

    try:
        while True:
            console.print("\n[bold green]You:[/bold green] ", end="")
            user_input = input().strip()

            if user_input.lower() in ("exit", "quit", "q", ""):
                console.print("\n[yellow]Ending session...[/yellow]")
                break

            response = agent.run(user_input)
            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(response))

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
