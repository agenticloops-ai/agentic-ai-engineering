"""
Mock LLM Testing

Demonstrates how to test an agent's tool-use loop without making real API calls.
Uses unittest.mock to simulate Anthropic responses, verifying that the agent correctly
parses tool calls, executes tools, sends results back, and handles errors.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel

from shared.agent import ToolUseAgent
from shared.mock_helpers import create_mock_response, make_text_block, make_tool_use_block

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


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
