"""
Integration Testing with Response Cassettes

Demonstrates how to test the full agent loop using recorded API responses instead of mocks.
By capturing real LLM responses to JSON cassette files, you get deterministic tests that
exercise the real response parsing path — no MagicMock shapes to maintain.

Key testing concepts:
- Cassette recorder: capture real API responses to JSON, replay them in tests
- Full loop testing: test multi-turn agent conversations with recorded responses
- Snapshot regression: compare agent output against golden baselines, detect drift
"""

import json
from pathlib import Path
from typing import Any

import pytest
from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel

from shared.agent import ToolUseAgent

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Cassette system — record and replay API responses
# ---------------------------------------------------------------------------


class CassetteResponse:
    """Reconstructed response object that mimics the Anthropic API response shape."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.stop_reason = data["stop_reason"]
        self.content = [self._build_block(block) for block in data["content"]]
        self.usage = self._build_usage(data.get("usage", {}))

    def _build_block(self, block: dict[str, Any]) -> Any:
        """Convert a serialized block back into an object with the right attributes."""
        return _AttrDict(block)

    def _build_usage(self, usage: dict[str, Any]) -> Any:
        """Convert serialized usage data back into an object."""
        return _AttrDict(
            {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
            }
        )


class _AttrDict:
    """Lightweight object that exposes dict keys as attributes."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        for key, value in data.items():
            setattr(self, key, value)


class CassetteClient:
    """A fake Anthropic client that replays responses from a cassette file."""

    def __init__(self, cassette_path: Path) -> None:
        with cassette_path.open(encoding="utf-8") as f:
            self._interactions = json.load(f)
        self._call_index = 0
        # Expose messages.create like the real Anthropic client
        self.messages = self

    def create(self, **kwargs: Any) -> CassetteResponse:
        """Replay the next recorded response."""
        if self._call_index >= len(self._interactions):
            raise RuntimeError(
                f"Cassette exhausted: expected at most {len(self._interactions)} API calls, "
                f"but got call #{self._call_index + 1}. "
                "The agent's behavior has diverged from the recording."
            )
        interaction = self._interactions[self._call_index]
        self._call_index += 1
        logger.info(
            "Replaying cassette response %d/%d",
            self._call_index,
            len(self._interactions),
        )
        return CassetteResponse(interaction["response"])

    @property
    def calls_remaining(self) -> int:
        """How many recorded responses are left to replay."""
        return len(self._interactions) - self._call_index


def serialize_response(response: Any) -> dict[str, Any]:
    """Serialize an Anthropic API response to a JSON-safe dict for recording."""
    content = []
    for block in response.content:
        if hasattr(block, "text"):
            content.append({"text": block.text})
        elif hasattr(block, "name") and hasattr(block, "input"):
            content.append({"id": block.id, "name": block.name, "input": block.input})
    return {
        "stop_reason": response.stop_reason,
        "content": content,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", None),
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", None
            ),
        },
    }


# ---------------------------------------------------------------------------
# Cassette fixtures — pre-built JSON data for testing
# ---------------------------------------------------------------------------

# Cassette: simple text response (no tool use)
CASSETTE_TEXT_ONLY = [
    {
        "response": {
            "stop_reason": "end_turn",
            "content": [{"text": "Hello! I'm ready to help you with calculations."}],
            "usage": {"input_tokens": 120, "output_tokens": 15},
        }
    }
]

# Cassette: single tool call (calculator) followed by text response
CASSETTE_CALCULATOR = [
    {
        "response": {
            "stop_reason": "tool_use",
            "content": [
                {
                    "id": "toolu_01ABC",
                    "name": "calculator",
                    "input": {"operation": "multiply", "a": 12, "b": 15},
                }
            ],
            "usage": {"input_tokens": 150, "output_tokens": 40},
        }
    },
    {
        "response": {
            "stop_reason": "end_turn",
            "content": [{"text": "12 multiplied by 15 equals 180."}],
            "usage": {"input_tokens": 200, "output_tokens": 12},
        }
    },
]

# Cassette: multi-turn tool use — two sequential calculator calls
CASSETTE_MULTI_TOOL = [
    {
        "response": {
            "stop_reason": "tool_use",
            "content": [
                {
                    "id": "toolu_01STEP1",
                    "name": "calculator",
                    "input": {"operation": "add", "a": 100, "b": 200},
                }
            ],
            "usage": {"input_tokens": 160, "output_tokens": 35},
        }
    },
    {
        "response": {
            "stop_reason": "tool_use",
            "content": [
                {
                    "id": "toolu_01STEP2",
                    "name": "calculator",
                    "input": {"operation": "multiply", "a": 300, "b": 2},
                }
            ],
            "usage": {"input_tokens": 220, "output_tokens": 38},
        }
    },
    {
        "response": {
            "stop_reason": "end_turn",
            "content": [
                {"text": "First I added 100 + 200 = 300, then multiplied by 2 to get 600."}
            ],
            "usage": {"input_tokens": 280, "output_tokens": 25},
        }
    },
]

# Cassette: blocked command — LLM requests rm, agent blocks it, LLM apologizes
CASSETTE_BLOCKED_COMMAND = [
    {
        "response": {
            "stop_reason": "tool_use",
            "content": [
                {
                    "id": "toolu_01DANGER",
                    "name": "run_bash",
                    "input": {"command": "rm -rf /tmp/data"},
                }
            ],
            "usage": {"input_tokens": 140, "output_tokens": 30},
        }
    },
    {
        "response": {
            "stop_reason": "end_turn",
            "content": [{"text": "I apologize, but that command was blocked for safety reasons."}],
            "usage": {"input_tokens": 210, "output_tokens": 18},
        }
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cassette_dir(tmp_path: Path) -> Path:
    """Create a temporary cassette directory."""
    d = tmp_path / "cassettes"
    d.mkdir()
    return d


def write_cassette(cassette_dir: Path, name: str, data: list[dict[str, Any]]) -> Path:
    """Write a cassette file and return its path."""
    path = cassette_dir / f"{name}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


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


# ---------------------------------------------------------------------------
# main() — run tests with Rich output for standalone execution
# ---------------------------------------------------------------------------


def main() -> None:
    """Run tests programmatically and display results with Rich."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Integration Testing with Response Cassettes[/bold cyan]\n\n"
            "Tests the full agent loop using pre-recorded API responses.\n"
            "No API keys required — responses are replayed from cassette files.\n\n"
            "Concepts: record/replay, cassette files, snapshot regression, token budgets",
            title="04 — Integration Testing",
        )
    )

    console.print("\n[bold]Running tests...[/bold]\n")

    # Save test results to output/
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "04_integration_testing.xml"

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
        console.print("\n[bold green]All integration tests passed![/bold green]")
    else:
        console.print(f"\n[bold red]Some tests failed (exit code: {exit_code})[/bold red]")

    console.print(f"[dim]Test report saved to {report_path}[/dim]")


if __name__ == "__main__":
    main()
