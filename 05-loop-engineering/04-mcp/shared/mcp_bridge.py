"""
Bridge between MCP servers and an LLM's tool-calling API.

Connects to any number of servers, then exposes their tools in each provider's format and routes
calls back to the server that owns them. The agent loop never needs to know MCP exists.
"""

import json
from collections.abc import Collection
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult, TextContent, Tool

from common import setup_logging

logger = setup_logging(__name__)

SEPARATOR = "__"


@dataclass(frozen=True)
class BridgedTool:
    """A discovered tool, along with the server it came from."""

    server: str
    tool: Tool

    @property
    def qualified_name(self) -> str:
        """Prefix the server name so two servers can each have a tool called "search"."""
        return f"{self.server}{SEPARATOR}{self.tool.name}"


class MCPBridge:
    """Owns MCP client connections and translates tool schemas and tool calls."""

    def __init__(
        self,
        servers: dict[str, StdioServerParameters],
        allowed_tools: Collection[str] | None = None,
    ) -> None:
        self.servers = servers
        self.allowed_tools = allowed_tools
        self.clients: dict[str, Client] = {}
        self.tools: dict[str, BridgedTool] = {}

    async def __aenter__(self) -> Self:
        for name, params in self.servers.items():
            client = Client(params)
            await client.__aenter__()
            self.clients[name] = client
            await self._discover(name, client)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Close in reverse order: the SDK's task scopes must unwind like nested "async with"s
        for client in reversed(list(self.clients.values())):
            await client.__aexit__(exc_type, exc, traceback)

    async def _discover(self, server: str, client: Client) -> None:
        """List a server's tools, keeping only the ones this agent is allowed to see."""
        listing = await client.list_tools()
        for tool in listing.tools:
            bridged = BridgedTool(server, tool)
            # A tool's description reaches the model, so hiding a tool beats blocking its calls
            if self.allowed_tools is None or bridged.qualified_name in self.allowed_tools:
                self.tools[bridged.qualified_name] = bridged
            else:
                logger.info(f"Hiding {bridged.qualified_name}: not on the allowlist")

    def anthropic_tools(self) -> list[Any]:
        """Format tools for Anthropic's Messages API, sorted to keep the request prefix stable."""
        return [
            {
                "name": name,
                "description": bridged.tool.description or "",
                "input_schema": bridged.tool.input_schema,
            }
            for name, bridged in sorted(self.tools.items())
        ]

    def openai_tools(self) -> list[Any]:
        """Format tools for OpenAI's Responses API."""
        return [
            {
                "type": "function",
                "name": name,
                "description": bridged.tool.description or "",
                "parameters": bridged.tool.input_schema,
                # MCP schemas have optional parameters, which strict mode doesn't allow
                "strict": False,
            }
            for name, bridged in sorted(self.tools.items())
        ]

    async def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Route a call to its server and return (text, is_error) for the tool result."""
        bridged = self.tools.get(qualified_name)
        if bridged is None:
            return f"Unknown tool: {qualified_name}", True
        try:
            result = await self.clients[bridged.server].call_tool(bridged.tool.name, arguments)
        except Exception as e:
            logger.error(f"MCP call to {qualified_name} failed: {e}")
            return f"Error calling {qualified_name}: {e}", True
        return flatten_result(result), bool(result.is_error)


def flatten_result(result: CallToolResult) -> str:
    """Turn an MCP result into text, preferring structured output when the server sends it."""
    if result.structured_content is not None and not result.is_error:
        return json.dumps(result.structured_content)
    parts = [
        block.text if isinstance(block, TextContent) else f"[{block.type} content omitted]"
        for block in result.content
    ]
    return "\n".join(parts)
