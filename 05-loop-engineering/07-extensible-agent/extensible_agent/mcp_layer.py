"""Layer: MCP. Tools discovered from external servers, adapted to the shared Tool contract."""

import json
from collections.abc import Collection
from types import TracebackType
from typing import Any, Self

from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult, TextContent

from common import setup_logging
from extensible_agent.tools import Tool, ToolOutput

logger = setup_logging(__name__)

SEPARATOR = "__"


def flatten_result(result: CallToolResult) -> str:
    """Turn an MCP result into text, preferring structured output when the server sends it."""
    if result.structured_content is not None and not result.is_error:
        return json.dumps(result.structured_content)
    return "\n".join(
        block.text if isinstance(block, TextContent) else f"[{block.type} content omitted]"
        for block in result.content
    )


class MCPLayer:
    """Owns the client connections and exposes only the allowlisted tools."""

    def __init__(
        self, servers: dict[str, StdioServerParameters], allowed_tools: Collection[str]
    ) -> None:
        self.servers = servers
        self.allowed_tools = allowed_tools
        self.clients: dict[str, Client] = {}
        self.discovered: list[Tool] = []
        self.hidden: list[str] = []

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
        for client in reversed(list(self.clients.values())):
            await client.__aexit__(exc_type, exc, traceback)

    async def _discover(self, server: str, client: Client) -> None:
        listing = await client.list_tools()
        for tool in listing.tools:
            qualified = f"{server}{SEPARATOR}{tool.name}"
            # A hidden tool's description never reaches the model
            if qualified not in self.allowed_tools:
                self.hidden.append(qualified)
                continue

            async def handler(tool_input: dict[str, Any], remote: str = tool.name) -> ToolOutput:
                try:
                    result = await client.call_tool(remote, tool_input)
                except Exception as e:
                    logger.error(f"MCP call to {remote} failed: {e}")
                    return f"Error calling {remote}: {e}", True
                return flatten_result(result), bool(result.is_error)

            self.discovered.append(
                Tool(qualified, tool.description or "", tool.input_schema, handler)
            )

    def tools(self) -> list[Tool]:
        """Expose the discovered tools; the loop can't tell these apart from local ones."""
        return self.discovered
