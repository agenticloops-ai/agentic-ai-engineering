"""
The contract every capability layer shares: a Tool is a schema plus an async handler.

Nothing in the agent loop knows whether a tool is local, sandboxed, remote over MCP, or a whole
child agent. That's what lets each layer stay independent.
"""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

ToolOutput = tuple[str, bool]
ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolOutput]]


@dataclass(frozen=True)
class Tool:
    """A callable capability as the agent sees it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


class ToolSet:
    """An immutable set of tools, fixed for the life of a conversation."""

    def __init__(self, tools: Iterable[Tool]) -> None:
        self.tools = {tool.name: tool for tool in tools}
        # Sorted and frozen: changing tools mid-conversation would invalidate the prompt cache
        # and every earlier thinking block
        self.schemas: list[Any] = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for _, t in sorted(self.tools.items())
        ]

    async def call(self, name: str, tool_input: dict[str, Any]) -> ToolOutput:
        """Run a tool, turning any failure into an error result the model can act on."""
        tool = self.tools.get(name)
        if tool is None:
            return f"Unknown tool: {name}", True
        try:
            return await tool.handler(tool_input)
        except (OSError, ValueError, KeyError) as e:
            return f"Error: {e}", True
