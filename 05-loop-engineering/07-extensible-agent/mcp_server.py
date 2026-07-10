"""
MCP Server for the capstone.

A minimal FastMCP server exposing a couple of deterministic tools over stdio. The
capstone agent spawns this as a subprocess and discovers these tools at runtime,
alongside its built-in run_python and spawn_subagent tools.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("extensible-agent-demo")


@mcp.tool()
def word_count(text: str) -> int:
    """Count the number of whitespace-separated words in the text."""
    return len(text.split())


@mcp.tool()
def prime_factors(n: int) -> list[int]:
    """Return the prime factors of n in ascending order."""
    if n < 2:
        return []
    factors: list[int] = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors


if __name__ == "__main__":
    mcp.run()
