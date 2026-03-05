"""
Mock LLM Testing

Demonstrates how to test an agent's tool-use loop without making real API calls.
Uses unittest.mock to simulate Anthropic responses, verifying that the agent correctly
parses tool calls, executes tools, sends results back, and handles errors.
"""

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from common import AnthropicTokenTracker, setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Tool definitions (same as 01-foundations/04-tool-use)
# ---------------------------------------------------------------------------

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
    {
        "name": "read_file",
        "description": "Reads the contents of a file at the specified path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_lines": {"type": "integer", "default": 100},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_bash",
        "description": "Executes a bash command and returns the output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        },
    },
]

BLOCKED_COMMANDS = ["rm", "sudo", "chmod", "chown", "mkfs", "dd", "shutdown", "reboot", ">", ">>"]


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def calculator(operation: str, a: float, b: float) -> dict[str, Any]:
    """Execute calculator tool."""
    operations = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else "Error: Division by zero",
    }
    result = operations[operation](a, b)
    return {"result": result, "operation": operation, "operands": [a, b]}


def read_file(path: str, max_lines: int = 100) -> dict[str, Any]:
    """Read the contents of a file."""
    try:
        with Path(path).open(encoding="utf-8") as f:
            lines = f.readlines()
        content = "".join(lines[:max_lines])
        return {"path": path, "content": content, "total_lines": len(lines)}
    except FileNotFoundError:
        return {"error": f"File not found: {path}"}


def run_bash(command: str, timeout: int = 30) -> dict[str, Any]:
    """Execute a bash command and return the output."""
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return {"error": f"Command blocked for safety: contains '{blocked}'"}
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout} seconds"}


TOOL_FUNCTIONS: dict[str, Any] = {
    "calculator": calculator,
    "read_file": read_file,
    "run_bash": run_bash,
}


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> Any:
    """Execute a tool and return its result."""
    if tool_name not in TOOL_FUNCTIONS:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return TOOL_FUNCTIONS[tool_name](**tool_input)
    except Exception as e:
        logger.error("Tool execution error: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Agent under test — refactored with dependency injection
# ---------------------------------------------------------------------------


class ToolUseAgent:
    """Tool-use agent with dependency injection for testability."""

    def __init__(self, client: Any, model: str = "claude-sonnet-4-5-20250929") -> None:
        self.client = client
        self.model = model
        self.messages: list[dict[str, Any]] = []
        self.token_tracker = AnthropicTokenTracker()

    def send_message(self, user_message: str) -> str:
        """Send a message and process the agent loop until a text response."""
        self.messages.append({"role": "user", "content": user_message})

        while True:
            logger.info("API call (messages: %d)", len(self.messages))

            # KEY CONCEPT: The injected client is called here — easy to mock
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=TOOLS,
                messages=self.messages,
            )

            self.token_tracker.track(response.usage)

            tool_uses = []
            text_content = []

            for block in response.content:
                if hasattr(block, "text"):
                    text_content.append(block.text)
                elif hasattr(block, "name") and hasattr(block, "input"):
                    tool_uses.append(block)

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use" or not tool_uses:
                return "\n".join(text_content) if text_content else ""

            # Execute each tool and send results back
            tool_results = []
            for tool_use in tool_uses:
                result = execute_tool(tool_use.name, tool_use.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result),
                    }
                )

            self.messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def create_mock_response(
    content: list[Any],
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> MagicMock:
    """Create a mock Anthropic API response."""
    response = MagicMock()
    response.content = content
    response.stop_reason = stop_reason
    # Mock the usage object to match Anthropic's structure
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    response.usage.cache_read_input_tokens = None
    response.usage.cache_creation_input_tokens = None
    return response


def make_text_block(text: str) -> Mock:
    """Create a mock TextBlock."""
    block = Mock()
    block.text = text
    # Ensure it does NOT look like a tool use block
    block.name = None
    block.input = None
    del block.name
    del block.input
    return block


def make_tool_use_block(tool_id: str, name: str, tool_input: dict[str, Any]) -> Mock:
    """Create a mock ToolUseBlock."""
    block = Mock()
    block.id = tool_id
    block.name = name
    block.input = tool_input
    # Ensure it does NOT look like a text block
    block.text = None
    del block.text
    return block


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestToolUseAgent:
    """Tests for the ToolUseAgent with mocked LLM responses."""

    def setup_method(self) -> None:
        """Create a fresh agent with a mock client for each test."""
        self.mock_client = MagicMock()
        self.agent = ToolUseAgent(client=self.mock_client)

    def test_agent_calls_calculator_tool(self) -> None:
        """Verify the agent executes calculator when LLM requests it."""
        # First response: LLM asks to use calculator
        tool_block = make_tool_use_block(
            "call_1",
            "calculator",
            {
                "operation": "multiply",
                "a": 6,
                "b": 7,
            },
        )
        tool_response = create_mock_response([tool_block], stop_reason="tool_use")

        # Second response: LLM returns final text
        text_block = make_text_block("The result is 42.")
        text_response = create_mock_response([text_block], stop_reason="end_turn")

        self.mock_client.messages.create.side_effect = [tool_response, text_response]

        result = self.agent.send_message("What is 6 * 7?")

        assert result == "The result is 42."
        assert self.mock_client.messages.create.call_count == 2

        # Verify tool result was sent back to the LLM
        tool_result_msg = self.agent.messages[2]  # user -> assistant -> tool_result
        assert tool_result_msg["role"] == "user"
        tool_result_data = json.loads(tool_result_msg["content"][0]["content"])
        assert tool_result_data["result"] == 42

    def test_agent_handles_text_response(self) -> None:
        """Verify the agent returns text directly when no tools are called."""
        text_block = make_text_block("Hello! How can I help you?")
        response = create_mock_response([text_block], stop_reason="end_turn")
        self.mock_client.messages.create.return_value = response

        result = self.agent.send_message("Hi there")

        assert result == "Hello! How can I help you?"
        # Only one API call — no tool loop
        assert self.mock_client.messages.create.call_count == 1

    def test_agent_handles_multi_turn_tool_use(self) -> None:
        """Verify the agent loops: tool_use -> result -> text."""
        # Turn 1: LLM requests calculator
        tool_block = make_tool_use_block(
            "call_1",
            "calculator",
            {
                "operation": "add",
                "a": 10,
                "b": 20,
            },
        )
        # Turn 2: LLM returns final answer
        text_block = make_text_block("10 + 20 = 30")

        self.mock_client.messages.create.side_effect = [
            create_mock_response([tool_block], stop_reason="tool_use"),
            create_mock_response([text_block], stop_reason="end_turn"),
        ]

        result = self.agent.send_message("Add 10 and 20")

        assert result == "10 + 20 = 30"
        # Messages: user, assistant(tool_use), user(tool_result), assistant(text)
        assert len(self.agent.messages) == 4

    def test_agent_sends_tool_results_back(self) -> None:
        """Verify tool results are formatted correctly in the message history."""
        tool_block = make_tool_use_block(
            "call_abc",
            "calculator",
            {
                "operation": "divide",
                "a": 100,
                "b": 4,
            },
        )
        text_block = make_text_block("25")

        self.mock_client.messages.create.side_effect = [
            create_mock_response([tool_block], stop_reason="tool_use"),
            create_mock_response([text_block], stop_reason="end_turn"),
        ]

        self.agent.send_message("Divide 100 by 4")

        # Find the tool_result message
        tool_result_msg = self.agent.messages[2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "call_abc"

    def test_agent_tracks_tokens(self) -> None:
        """Verify token tracking accumulates across API calls."""
        text_block = make_text_block("Done")
        response = create_mock_response(
            [text_block], stop_reason="end_turn", input_tokens=150, output_tokens=75
        )
        self.mock_client.messages.create.return_value = response

        self.agent.send_message("Hello")

        assert self.agent.token_tracker.total_input_tokens == 150
        assert self.agent.token_tracker.total_output_tokens == 75

    def test_agent_handles_api_error(self) -> None:
        """Verify the agent propagates API errors."""
        self.mock_client.messages.create.side_effect = Exception("API rate limit exceeded")

        with pytest.raises(Exception, match="API rate limit exceeded"):
            self.agent.send_message("Hello")


# ---------------------------------------------------------------------------
# main() — run tests with Rich output for standalone execution
# ---------------------------------------------------------------------------


def main() -> None:
    """Run tests programmatically and display results with Rich."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Mock LLM Testing[/bold cyan]\n\n"
            "Tests the tool-use agent loop using mocked Anthropic responses.\n"
            "No API keys required — everything is simulated.\n\n"
            "Concepts: dependency injection, mock responses, assertion strategies",
            title="01 — Mock LLM Testing",
        )
    )

    console.print("\n[bold]Running tests...[/bold]\n")

    # Save test results to output/
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "01_mock_llm_testing.xml"

    exit_code = pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "--no-header",
            f"--junitxml={report_path}",
        ]
    )

    if exit_code == 0:
        console.print("\n[bold green]All tests passed![/bold green]")
    else:
        console.print(f"\n[bold red]Some tests failed (exit code: {exit_code})[/bold red]")

    console.print(f"[dim]Test report saved to {report_path}[/dim]")


if __name__ == "__main__":
    main()
