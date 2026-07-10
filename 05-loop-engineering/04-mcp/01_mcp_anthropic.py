"""
MCP Integration (Anthropic)

Instead of hand-coding tools, discover them from a Model Context Protocol server
at runtime. This client spawns 03_mcp_server.py over stdio, lists its tools,
bridges the MCP schemas into Anthropic's tool format, and runs the usual agent
loop — executing each tool call back through the MCP session.

The loop is async because MCP calls are async; everything else is the Foundations
agent loop.
"""

import asyncio
import sys
from typing import Any

import anthropic
from anthropic.types import TextBlock, ToolUseBlock
from dotenv import find_dotenv, load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import AnthropicTokenTracker

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

SYSTEM_PROMPT = """You are an assistant whose tools are provided by an MCP server.
Use them to answer the user's request, then summarize the result."""

SERVER = StdioServerParameters(command=sys.executable, args=["03_mcp_server.py"])


def to_anthropic_tools(mcp_tools: Any) -> list[dict[str, Any]]:
    """Bridge MCP tool definitions into Anthropic's tool schema."""
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        }
        for t in mcp_tools
    ]


def extract_text(result: Any) -> str:
    """Flatten an MCP call_tool result into a plain string."""
    parts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
    text = "\n".join(parts) if parts else "(no output)"
    return f"Error: {text}" if result.isError else text


class MCPAgent:
    """Agent whose tools are discovered from and executed through an MCP server."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = AnthropicTokenTracker()

    async def run(self, session: ClientSession, tools: list[dict[str, Any]], task: str) -> str:
        """Execute the agent loop, routing tool calls to the MCP session."""
        logger.info(f"Task: {task}")
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

        for iteration in range(self.max_iterations):
            logger.info(f"--- Iteration {iteration + 1} ---")
            response = self.client.messages.create(
                model=self.model,
                temperature=0.1,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            assistant_content = []
            for block in response.content:
                if isinstance(block, TextBlock):
                    logger.info(f"🤖 Agent: {block.text}")
                    assistant_content.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    logger.info(f"🔌 MCP tool: {block.name}({block.input})")
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                return response.content[0].text if response.content else "Done"

            tool_results = []
            for block in response.content:
                if isinstance(block, ToolUseBlock):
                    call = await session.call_tool(block.name, dict(block.input))
                    result = extract_text(call)
                    logger.info(f"📋 Result: {result[:100]}")
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result}
                    )
            messages.append({"role": "user", "content": tool_results})

        return "Max iterations reached"


async def main_async() -> None:
    """Open the MCP session, discover tools, and run the interactive loop."""
    console = Console()
    agent = MCPAgent()

    async with stdio_client(SERVER) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listing = await session.list_tools()
        tools = to_anthropic_tools(listing.tools)

        console.print(
            Panel(
                f"Connected to MCP server. Discovered tools: "
                f"{', '.join(t['name'] for t in tools)}\n\n"
                "Try:\n"
                "  - How many words are in 'the quick brown fox'?\n"
                "  - What is the 20th Fibonacci number?\n\n"
                "Type 'quit' to exit.",
                title="MCP Integration (Anthropic)",
            )
        )

        try:
            while True:
                console.print("\n[bold green]You:[/bold green] ", end="")
                user_input = input().strip()
                if user_input.lower() in ("exit", "quit", "q", ""):
                    console.print("\n[yellow]Ending session...[/yellow]")
                    break
                response = await agent.run(session, tools, user_input)
                console.print("\n[bold blue]Agent:[/bold blue]")
                console.print(Markdown(response))
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    agent.token_tracker.report()


def main() -> None:
    """Entry point wrapping the async MCP session."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
