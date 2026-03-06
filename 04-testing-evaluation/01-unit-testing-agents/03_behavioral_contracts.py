"""
Behavioral Contracts

Demonstrates how to define and verify behavioral invariants — things an agent
must ALWAYS or NEVER do — regardless of what the LLM returns.

Key testing concepts:
- Safety contracts: blocked commands are never executed, even if the LLM requests them
- Termination guarantees: the agent stops after max_iterations, preventing infinite loops
- History invariants: tool results always appear in message history after execution
- Robustness: agent handles empty responses, malformed tool input gracefully
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
# Behavioral contract tests
# ---------------------------------------------------------------------------


class TestSafetyContracts:
    """CONTRACT: The agent must never execute blocked commands."""

    def setup_method(self) -> None:
        """Create a fresh agent with a mock client for each test."""
        self.mock_client = MagicMock()
        self.agent = ToolUseAgent(client=self.mock_client, max_iterations=5)

    def test_agent_never_executes_blocked_commands(self) -> None:
        """Even when the LLM requests rm -rf /, the tool returns an error."""
        # LLM requests a dangerous command
        tool_block = make_tool_use_block("call_1", "run_bash", {"command": "rm -rf /"})
        tool_response = create_mock_response([tool_block], stop_reason="tool_use")

        # After seeing the error, LLM gives a text response
        text_block = make_text_block("I cannot execute that command.")
        text_response = create_mock_response([text_block], stop_reason="end_turn")

        self.mock_client.messages.create.side_effect = [tool_response, text_response]

        self.agent.send_message("Delete everything")

        # Verify the tool result contains a blocked error
        tool_result_msg = self.agent.messages[2]
        tool_result_data = json.loads(tool_result_msg["content"][0]["content"])
        assert "error" in tool_result_data
        assert "blocked" in tool_result_data["error"].lower()

    def test_blocked_sudo_command(self) -> None:
        """Verify sudo commands are blocked."""
        tool_block = make_tool_use_block("call_1", "run_bash", {"command": "sudo apt install foo"})
        tool_response = create_mock_response([tool_block], stop_reason="tool_use")
        text_block = make_text_block("Cannot run sudo.")
        text_response = create_mock_response([text_block], stop_reason="end_turn")

        self.mock_client.messages.create.side_effect = [tool_response, text_response]

        self.agent.send_message("Install a package")

        tool_result_msg = self.agent.messages[2]
        tool_result_data = json.loads(tool_result_msg["content"][0]["content"])
        assert "error" in tool_result_data
        assert "sudo" in tool_result_data["error"]


class TestTerminationContracts:
    """CONTRACT: The agent must always terminate within max_iterations."""

    def setup_method(self) -> None:
        """Create agent with a low iteration limit for testing."""
        self.mock_client = MagicMock()
        self.agent = ToolUseAgent(client=self.mock_client, max_iterations=3)

    def test_agent_stops_after_max_iterations(self) -> None:
        """If the LLM keeps requesting tools, the agent stops at max_iterations."""
        # LLM always requests a tool — never gives a final answer
        tool_block = make_tool_use_block(
            "call_n",
            "calculator",
            {
                "operation": "add",
                "a": 1,
                "b": 1,
            },
        )
        infinite_response = create_mock_response([tool_block], stop_reason="tool_use")
        self.mock_client.messages.create.return_value = infinite_response

        result = self.agent.send_message("Keep calculating forever")

        # Agent must stop and return the safety message
        assert "maximum iterations reached" in result.lower()
        # Exactly max_iterations API calls
        assert self.mock_client.messages.create.call_count == 3


class TestHistoryContracts:
    """CONTRACT: Tool results must always appear in the message history."""

    def setup_method(self) -> None:
        """Create a fresh agent with a mock client."""
        self.mock_client = MagicMock()
        self.agent = ToolUseAgent(client=self.mock_client)

    def test_agent_always_includes_tool_results(self) -> None:
        """After tool execution, the result must be in the conversation history."""
        tool_block = make_tool_use_block(
            "call_1",
            "calculator",
            {
                "operation": "multiply",
                "a": 3,
                "b": 9,
            },
        )
        text_block = make_text_block("27")

        self.mock_client.messages.create.side_effect = [
            create_mock_response([tool_block], stop_reason="tool_use"),
            create_mock_response([text_block], stop_reason="end_turn"),
        ]

        self.agent.send_message("3 * 9?")

        # Find all tool_result messages
        tool_result_messages = [
            msg
            for msg in self.agent.messages
            if msg["role"] == "user"
            and isinstance(msg["content"], list)
            and any(item.get("type") == "tool_result" for item in msg["content"])
        ]
        assert len(tool_result_messages) == 1

        # Verify the result content is valid JSON
        result_content = json.loads(tool_result_messages[0]["content"][0]["content"])
        assert result_content["result"] == 27

    def test_agent_preserves_conversation_history(self) -> None:
        """Messages must accumulate correctly across the agent loop."""
        text_block = make_text_block("Hello!")
        self.mock_client.messages.create.return_value = create_mock_response(
            [text_block], stop_reason="end_turn"
        )

        self.agent.send_message("Hi")

        # After a simple exchange: user message + assistant response
        assert len(self.agent.messages) == 2
        assert self.agent.messages[0]["role"] == "user"
        assert self.agent.messages[0]["content"] == "Hi"
        assert self.agent.messages[1]["role"] == "assistant"


class TestRobustnessContracts:
    """CONTRACT: The agent must handle edge cases gracefully."""

    def setup_method(self) -> None:
        """Create a fresh agent with a mock client."""
        self.mock_client = MagicMock()
        self.agent = ToolUseAgent(client=self.mock_client)

    def test_agent_handles_empty_response(self) -> None:
        """Empty content from the LLM should return an empty string, not crash."""
        response = create_mock_response([], stop_reason="end_turn")
        self.mock_client.messages.create.return_value = response

        result = self.agent.send_message("Say nothing")

        assert result == ""

    def test_agent_handles_malformed_tool_input(self) -> None:
        """If the LLM sends wrong arguments, the tool error is captured gracefully."""
        # LLM sends calculator with wrong keys
        tool_block = make_tool_use_block(
            "call_bad",
            "calculator",
            {
                "wrong_key": "not_a_number",
            },
        )
        tool_response = create_mock_response([tool_block], stop_reason="tool_use")

        text_block = make_text_block("Sorry, that did not work.")
        text_response = create_mock_response([text_block], stop_reason="end_turn")

        self.mock_client.messages.create.side_effect = [tool_response, text_response]

        self.agent.send_message("Do something wrong")

        # The agent should not crash — it should capture the error in tool results
        tool_result_msg = self.agent.messages[2]
        tool_result_data = json.loads(tool_result_msg["content"][0]["content"])
        assert "error" in tool_result_data

    def test_tool_results_format_is_consistent(self) -> None:
        """All tool results must have the same structure: type, tool_use_id, content."""
        # Execute two tools in sequence
        tool_block_1 = make_tool_use_block(
            "call_1",
            "calculator",
            {
                "operation": "add",
                "a": 1,
                "b": 2,
            },
        )
        tool_block_2 = make_tool_use_block(
            "call_2",
            "calculator",
            {
                "operation": "multiply",
                "a": 3,
                "b": 4,
            },
        )
        tool_response = create_mock_response([tool_block_1, tool_block_2], stop_reason="tool_use")

        text_block = make_text_block("Done")
        text_response = create_mock_response([text_block], stop_reason="end_turn")

        self.mock_client.messages.create.side_effect = [tool_response, text_response]

        self.agent.send_message("Calculate two things")

        # Find the tool_result message
        tool_result_msg = self.agent.messages[2]
        assert tool_result_msg["role"] == "user"

        # Verify each tool result has the required keys
        for item in tool_result_msg["content"]:
            assert "type" in item
            assert item["type"] == "tool_result"
            assert "tool_use_id" in item
            assert "content" in item
            # Content must be valid JSON
            parsed = json.loads(item["content"])
            assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# main() — run tests with Rich output for standalone execution
# ---------------------------------------------------------------------------


def main() -> None:
    """Run tests programmatically and display results with Rich."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Behavioral Contracts[/bold cyan]\n\n"
            "Verifies invariants the agent must ALWAYS or NEVER violate:\n\n"
            "  NEVER execute blocked commands (rm, sudo, etc.)\n"
            "  ALWAYS stop within max_iterations\n"
            "  ALWAYS include tool results in conversation history\n"
            "  ALWAYS handle edge cases without crashing\n\n"
            "Concepts: safety contracts, termination guarantees, history invariants",
            title="03 — Behavioral Contracts",
        )
    )

    console.print("\n[bold]Running tests...[/bold]\n")

    # Save test results to output/
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "03_behavioral_contracts.xml"

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
        console.print("\n[bold green]All behavioral contracts verified![/bold green]")
    else:
        console.print(f"\n[bold red]Some contracts violated (exit code: {exit_code})[/bold red]")

    console.print(f"[dim]Test report saved to {report_path}[/dim]")


if __name__ == "__main__":
    main()
