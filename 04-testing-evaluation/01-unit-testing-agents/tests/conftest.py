"""
Shared test fixtures and cassette infrastructure for integration tests.

Provides CassetteClient for record/replay testing, pre-built cassette data,
and fixtures used across test modules.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from common import setup_logging

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Cassette system — record and replay API responses
# ---------------------------------------------------------------------------


class CassetteResponse:
    """Reconstructed response object that mimics the Anthropic API response shape."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.stop_reason = data["stop_reason"]
        self.content = [_AttrDict(block) for block in data["content"]]
        self.usage = _AttrDict(
            {
                "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                "output_tokens": data.get("usage", {}).get("output_tokens", 0),
                "cache_read_input_tokens": data.get("usage", {}).get("cache_read_input_tokens"),
                "cache_creation_input_tokens": data.get("usage", {}).get(
                    "cache_creation_input_tokens"
                ),
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
# Pre-built cassette data
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
