"""
Mock response factories for testing Anthropic API interactions.

Provides helpers to create mock Anthropic API responses, text blocks,
and tool-use blocks without depending on the real SDK types.
"""

from typing import Any
from unittest.mock import MagicMock, Mock


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
