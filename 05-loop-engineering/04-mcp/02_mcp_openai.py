"""
MCP Integration (OpenAI)

The same runtime tool discovery as the Anthropic version, driven through the
OpenAI Responses API. This client spawns 03_mcp_server.py over stdio, lists its
tools, bridges the MCP schemas into OpenAI's function-tool format, and executes
each call back through the MCP session.

The loop is async because MCP calls are async; everything else is the Foundations
agent loop.
"""

import asyncio
import json
import sys
from typing import Any

from dotenv import find_dotenv, load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import OpenAITokenTracker

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

SYSTEM_PROMPT = """You are an assistant whose tools are provided by an MCP server.
Use them to answer the user's request, then summarize the result."""

SERVER = StdioServerParameters(command=sys.executable, args=["03_mcp_server.py"])


def to_openai_tools(mcp_tools: Any) -> list[dict[str, Any]]:
    """Bridge MCP tool definitions into OpenAI's function-tool schema."""
    return [
        {
            "type": "function",
            "name": t.name,
            "description": t.description or "",
            "parameters": t.inputSchema,
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

    def __init__(self, model: str = "gpt-4.1"):
        self.client = OpenAI()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = OpenAITokenTracker()

    async def run(self, session: ClientSession, tools: list[dict[str, Any]], task: str) -> str:
        """Execute the agent loop, routing tool calls to the MCP session."""
        logger.info(f"Task: {task}")
        input_messages: list[Any] = [{"role": "user", "content": task}]
        previous_response_id: str | None = None

        for iteration in range(self.max_iterations):
            logger.info(f"--- Iteration {iteration + 1} ---")
            response = self.client.responses.create(
                model=self.model,
                tools=tools,
                instructions=SYSTEM_PROMPT,
                input=input_messages,
                **({"previous_response_id": previous_response_id} if previous_response_id else {}),
            )
            if response.usage:
                self.token_tracker.track(response.usage)
            if response.output_text:
                logger.info(f"🤖 Agent: {response.output_text}")

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                return response.output_text or "Done"

            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError as e:
                    args = {}
                    logger.error(f"Invalid tool arguments: {e}")
                logger.info(f"🔌 MCP tool: {call.name}({json.dumps(args)})")
                mcp_result = await session.call_tool(call.name, args)
                result = extract_text(mcp_result)
                logger.info(f"📋 Result: {result[:100]}")
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"result": result}),
                    }
                )

            previous_response_id = response.id
            input_messages = tool_outputs

        return "Max iterations reached"


async def main_async() -> None:
    """Open the MCP session, discover tools, and run the interactive loop."""
    console = Console()
    agent = MCPAgent()

    async with stdio_client(SERVER) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listing = await session.list_tools()
        tools = to_openai_tools(listing.tools)

        console.print(
            Panel(
                f"Connected to MCP server. Discovered tools: "
                f"{', '.join(t['name'] for t in tools)}\n\n"
                "Try:\n"
                "  - How many words are in 'the quick brown fox'?\n"
                "  - What is the 20th Fibonacci number?\n\n"
                "Type 'quit' to exit.",
                title="MCP Integration (OpenAI)",
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
