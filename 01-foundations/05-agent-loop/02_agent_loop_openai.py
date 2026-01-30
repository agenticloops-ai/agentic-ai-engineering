"""
Agent Loop (OpenAI)

Demonstrates a minimal autonomous agent that:
- Takes a task from the user
- Decides which tools to use
- Executes tools in a loop until complete
"""

import json
import subprocess
from pathlib import Path
from typing import Any

from common.logging_config import setup_logging
from common.token_tracking import OpenAITokenTracker
from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel

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


# Tool definitions (OpenAI Responses API format)
TOOLS = [
    {
        "type": "function",
        "name": "read_file",
        "description": "Read the contents of a file at the given path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read",
                }
            },
            "additionalProperties": False,
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "write_file",
        "description": "Write content to a file at the given path.",
        "parameters": {
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
            "additionalProperties": False,
            "required": ["path", "content"],
        },
    },
    {
        "type": "function",
        "name": "bash",
        "description": "Execute a bash command and return its output.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                }
            },
            "additionalProperties": False,
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

    def __init__(self, model: str = "codex-mini-latest"):
        self.client = OpenAI()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = OpenAITokenTracker()

    def run(self, task: str) -> str:
        """Execute the agent loop for the given task."""
        logger.info(f"Task: {task}")

        input_messages: list[Any] = [{"role": "user", "content": task}]
        previous_response_id: str | None = None

        for iteration in range(self.max_iterations):
            logger.info(f"--- Iteration {iteration + 1} ---")

            # Call the model using responses API
            response = self.client.responses.create(
                model=self.model,
                temperature=0.1,
                tools=TOOLS,
                instructions=SYSTEM_PROMPT,
                input=input_messages,
                **({"previous_response_id": previous_response_id} if previous_response_id else {}),
            )

            if response.usage:
                self.token_tracker.track(response.usage)

            # Log any text output
            if response.output_text:
                logger.info(f"🤖 Agent: {response.output_text}")

            # Check if there are function calls
            function_calls = [o for o in response.output if o.type == "function_call"]

            # If no function calls, task is complete
            if not function_calls:
                return response.output_text or "Done"

            # Execute tools and collect results
            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError as e:
                    args = {}
                    logger.error(f"Invalid tool arguments: {e}")

                logger.info(f"🔧 Tool: {call.name}({json.dumps(args)})")
                result = execute_tool(call.name, args)
                logger.info(f"📋 Result: {result[:100]}{'...' if len(result) > 100 else ''}")

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"result": result}),
                    }
                )

            # Continue conversation with tool outputs
            previous_response_id = response.id
            input_messages = tool_outputs

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
            title="Coding Agent (OpenAI)",
        )
    )

    agent = CodingAgent()

    try:
        while True:
            user_input = input("You: ")
            if user_input.lower() in ("exit", "quit", "q"):
                break
            response = agent.run(user_input)
            print(f"Agent: {response}")
    except KeyboardInterrupt:
        print("\nInterrupted")

    agent.token_tracker.report()


if __name__ == "__main__":
    main()
