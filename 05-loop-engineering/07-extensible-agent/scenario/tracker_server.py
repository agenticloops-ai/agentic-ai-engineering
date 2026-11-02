"""An issue tracker published over MCP, standing in for an external system the agent doesn't own."""

import logging
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

# stdout carries the MCP protocol on the stdio transport, so logging must go to stderr
logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(message)s")

mcp = MCPServer("issue-tracker")

ISSUES: dict[int, dict[str, object]] = {
    101: {
        "id": 101,
        "title": "Customers can buy more units than we have in stock",
        "body": "A customer reserved 11 units of a SKU with 10 in stock, and the order went through.",
        "triage": None,
    },
    102: {
        "id": 102,
        "title": "Inventory value report is wrong after discounts",
        "body": "Report shows 0 for items priced under 1.00 when a 10% discount is applied.",
        "triage": None,
    },
    103: {
        "id": 103,
        "title": "Restocking with a negative quantity raises an error",
        "body": "restock('SKU-1', -5) raises ValueError. We expected it to reduce the stock.",
        "triage": None,
    },
}


def get_or_fail(issue_id: int) -> dict[str, object]:
    """Look up an issue, reporting a missing one to the client."""
    if issue_id not in ISSUES:
        raise ToolError(f"No issue with id {issue_id}")
    return ISSUES[issue_id]


@mcp.tool()
def list_issues() -> list[dict[str, object]]:
    """List every issue with its current triage status."""
    return list(ISSUES.values())


@mcp.tool()
def set_triage(issue_id: int, verdict: str, severity: str, root_cause: str) -> dict[str, object]:
    """Record a triage result. Verdict is 'bug' or 'not-a-bug'; severity is 'low' to 'critical'."""
    issue = get_or_fail(issue_id)
    issue["triage"] = {"verdict": verdict, "severity": severity, "root_cause": root_cause}
    return issue


@mcp.tool()
def delete_issue(issue_id: int) -> str:
    """Permanently delete an issue. The agent's allowlist deliberately leaves this one out."""
    get_or_fail(issue_id)
    del ISSUES[issue_id]
    return f"Deleted issue {issue_id}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
