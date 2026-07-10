"""
MCP Server

A minimal Model Context Protocol server built with FastMCP. It exposes three
deterministic tools over stdio. The client scripts spawn this file as a
subprocess, discover these tools at runtime, and let the agent call them.

Run it directly to sanity-check it (it will wait on stdio):
    uv run --directory 05-loop-engineering/04-mcp python 03_mcp_server.py
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("loop-engineering-demo")


@mcp.tool()
def word_count(text: str) -> int:
    """Count the number of whitespace-separated words in the text."""
    return len(text.split())


@mcp.tool()
def to_uppercase(text: str) -> str:
    """Return the text uppercased."""
    return text.upper()


@mcp.tool()
def fibonacci(n: int) -> int:
    """Return the nth Fibonacci number (0-indexed, F(0)=0, F(1)=1)."""
    if n < 0:
        raise ValueError("n must be non-negative")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


if __name__ == "__main__":
    mcp.run()
