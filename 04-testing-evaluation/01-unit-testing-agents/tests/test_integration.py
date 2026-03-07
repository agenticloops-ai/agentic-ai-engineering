"""
Integration Testing with Response Cassettes

Tests the full agent loop using recorded API responses instead of mocks.
By replaying pre-recorded responses from cassette files, you get deterministic tests that
exercise the real response parsing path — no MagicMock shapes to maintain.

Key testing concepts:
- Full loop testing: test multi-turn agent conversations with recorded responses
- Snapshot regression: compare agent output against golden baselines, detect drift
- Cassette exhaustion: catches divergent agent behavior automatically
"""

import json
from pathlib import Path

import pytest

from shared.agent import ToolUseAgent
from tests.conftest import (
    CASSETTE_BLOCKED_COMMAND,
    CASSETTE_CALCULATOR,
    CASSETTE_MULTI_TOOL,
    CASSETTE_TEXT_ONLY,
    CassetteClient,
    CassetteResponse,
    serialize_response,
    write_cassette,
)


# ---------------------------------------------------------------------------
# Tests — full agent loop with cassette replay
# ---------------------------------------------------------------------------


class TestCassetteReplay:
    """Integration tests using pre-recorded API responses."""

    def test_text_only_response(self, cassette_dir: Path) -> None:
        """Agent returns text directly when no tools are needed."""
        path = write_cassette(cassette_dir, "text_only", CASSETTE_TEXT_ONLY)
        client = CassetteClient(path)
        agent = ToolUseAgent(client=client)

        result = agent.send_message("Hi there")

        assert result == "Hello! I'm ready to help you with calculations."
        assert client.calls_remaining == 0

    def test_single_tool_call(self, cassette_dir: Path) -> None:
        """Agent executes a calculator tool and returns the final answer."""
        path = write_cassette(cassette_dir, "calculator", CASSETTE_CALCULATOR)
        client = CassetteClient(path)
        agent = ToolUseAgent(client=client)

        result = agent.send_message("What is 12 * 15?")

        assert "180" in result
        assert client.calls_remaining == 0
        # Verify the tool was actually executed — result should be in message history
        tool_result_msg = agent.messages[2]
        tool_result_data = json.loads(tool_result_msg["content"][0]["content"])
        assert tool_result_data["result"] == 180

    def test_multi_turn_tool_use(self, cassette_dir: Path) -> None:
        """Agent handles multiple sequential tool calls across turns."""
        path = write_cassette(cassette_dir, "multi_tool", CASSETTE_MULTI_TOOL)
        client = CassetteClient(path)
        agent = ToolUseAgent(client=client)

        result = agent.send_message("Add 100 + 200, then multiply by 2")

        assert "600" in result
        assert client.calls_remaining == 0
        # 6 messages: user, assistant(tool), user(result), assistant(tool), user(result), assistant
        assert len(agent.messages) == 6

    def test_blocked_command_integration(self, cassette_dir: Path) -> None:
        """Full integration: LLM requests dangerous command, agent blocks it, LLM recovers."""
        path = write_cassette(cassette_dir, "blocked", CASSETTE_BLOCKED_COMMAND)
        client = CassetteClient(path)
        agent = ToolUseAgent(client=client)

        result = agent.send_message("Delete the temp data")

        assert "blocked" in result.lower() or "safety" in result.lower()
        # Verify the tool result contains the block error
        tool_result_msg = agent.messages[2]
        tool_result_data = json.loads(tool_result_msg["content"][0]["content"])
        assert "error" in tool_result_data
        assert "blocked" in tool_result_data["error"].lower()


class TestCassetteExhaustion:
    """Verify the cassette system catches divergent agent behavior."""

    def test_cassette_exhausted_raises_error(self, cassette_dir: Path) -> None:
        """If the agent makes more API calls than recorded, the cassette raises an error."""
        # Use text-only cassette (1 response) but set up agent to make 2 calls
        path = write_cassette(cassette_dir, "short", CASSETTE_TEXT_ONLY)
        client = CassetteClient(path)

        # First call succeeds
        response = client.create(model="test", max_tokens=100, tools=[], messages=[])
        assert response.stop_reason == "end_turn"

        # Second call should fail — cassette is exhausted
        with pytest.raises(RuntimeError, match="Cassette exhausted"):
            client.create(model="test", max_tokens=100, tools=[], messages=[])


# ---------------------------------------------------------------------------
# Tests — snapshot regression testing
# ---------------------------------------------------------------------------


class TestSnapshotRegression:
    """Compare agent output against golden snapshots to detect regressions."""

    def test_calculator_output_matches_snapshot(self, cassette_dir: Path) -> None:
        """Agent output for a known input must match the recorded golden snapshot."""
        path = write_cassette(cassette_dir, "calculator", CASSETTE_CALCULATOR)

        # Golden snapshot — the expected output for "What is 12 * 15?"
        golden_snapshot = "12 multiplied by 15 equals 180."

        client = CassetteClient(path)
        agent = ToolUseAgent(client=client)
        result = agent.send_message("What is 12 * 15?")

        assert result == golden_snapshot, (
            f"Output has drifted from snapshot.\n"
            f"  Expected: {golden_snapshot!r}\n"
            f"  Got:      {result!r}"
        )

    def test_message_history_shape_matches_snapshot(self, cassette_dir: Path) -> None:
        """The shape of the message history must match the expected pattern."""
        path = write_cassette(cassette_dir, "calculator", CASSETTE_CALCULATOR)
        client = CassetteClient(path)
        agent = ToolUseAgent(client=client)
        agent.send_message("What is 12 * 15?")

        # Snapshot of expected message roles in order
        expected_roles = ["user", "assistant", "user", "assistant"]
        actual_roles = [msg["role"] for msg in agent.messages]

        assert actual_roles == expected_roles, (
            f"Message history shape has changed.\n"
            f"  Expected: {expected_roles}\n"
            f"  Got:      {actual_roles}"
        )

    def test_token_usage_within_budget(self, cassette_dir: Path) -> None:
        """Total token usage must stay within the expected budget."""
        path = write_cassette(cassette_dir, "multi_tool", CASSETTE_MULTI_TOOL)
        client = CassetteClient(path)
        agent = ToolUseAgent(client=client)
        agent.send_message("Add 100 + 200, then multiply by 2")

        # Budget snapshot — if token usage spikes, something changed
        max_input_tokens = 1000
        max_output_tokens = 200

        assert agent.token_tracker.total_input_tokens <= max_input_tokens, (
            f"Input token budget exceeded: "
            f"{agent.token_tracker.total_input_tokens} > {max_input_tokens}"
        )
        assert agent.token_tracker.total_output_tokens <= max_output_tokens, (
            f"Output token budget exceeded: "
            f"{agent.token_tracker.total_output_tokens} > {max_output_tokens}"
        )


# ---------------------------------------------------------------------------
# Tests — serialization round-trip
# ---------------------------------------------------------------------------


class TestCassetteSerialization:
    """Verify that response serialization and deserialization are lossless."""

    def test_text_response_round_trip(self) -> None:
        """A text-only response survives serialize -> deserialize without data loss."""
        original_data = CASSETTE_TEXT_ONLY[0]["response"]
        response = CassetteResponse(original_data)
        serialized = serialize_response(response)

        assert serialized["stop_reason"] == "end_turn"
        assert len(serialized["content"]) == 1
        assert serialized["content"][0]["text"] == "Hello! I'm ready to help you with calculations."
        assert serialized["usage"]["input_tokens"] == 120

    def test_tool_use_response_round_trip(self) -> None:
        """A tool-use response survives serialize -> deserialize without data loss."""
        original_data = CASSETTE_CALCULATOR[0]["response"]
        response = CassetteResponse(original_data)
        serialized = serialize_response(response)

        assert serialized["stop_reason"] == "tool_use"
        assert serialized["content"][0]["name"] == "calculator"
        assert serialized["content"][0]["input"]["operation"] == "multiply"
        assert serialized["content"][0]["id"] == "toolu_01ABC"
