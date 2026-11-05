"""
MCP Server

A small task tracker published over the Model Context Protocol with MCPServer (the mcp 2.x name
for FastMCP). Type hints and docstrings become the tool schemas any MCP client can discover.

The agent scripts launch this file themselves, so you never need to start it by hand. To explore
it on its own, use the MCP Inspector (see the README).
"""

import logging
import sys
from dataclasses import asdict, dataclass
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

# On the stdio transport, stdout IS the protocol: one stray print() corrupts the session.
# All logging has to go to stderr, which is why this script skips the common Rich setup.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)

Priority = Literal["low", "medium", "high"]


@dataclass
class Task:
    """One entry in the tracker."""

    id: int
    title: str
    priority: Priority
    done: bool = False


class TaskStore:
    """In-memory task storage; it lives as long as the server process."""

    def __init__(self) -> None:
        self.tasks: dict[int, Task] = {}
        self.next_id = 1

    def add(self, title: str, priority: Priority) -> Task:
        """Create a task."""
        task = Task(self.next_id, title, priority)
        self.tasks[task.id] = task
        self.next_id += 1
        return task

    def complete(self, task_id: int) -> Task:
        """Mark a task as done."""
        if task_id not in self.tasks:
            # ToolError's message reaches the model; any other exception is hidden as internal
            raise ToolError(f"No task with id {task_id}")
        self.tasks[task_id].done = True
        return self.tasks[task_id]


mcp = MCPServer("task-tracker")
store = TaskStore()
store.add("Rotate the staging API keys", "high")
store.add("Update the onboarding docs", "low")


@mcp.tool()
def add_task(title: str, priority: Priority = "medium") -> dict[str, object]:
    """Add a task to the tracker and return it."""
    return asdict(store.add(title, priority))


@mcp.tool()
def list_tasks(include_done: bool = False) -> list[dict[str, object]]:
    """List tasks in the tracker, highest priority first."""
    order = {"high": 0, "medium": 1, "low": 2}
    tasks = [t for t in store.tasks.values() if include_done or not t.done]
    return [asdict(t) for t in sorted(tasks, key=lambda t: order[t.priority])]


@mcp.tool()
def complete_task(task_id: int) -> dict[str, object]:
    """Mark a task as done. Fails if no task has that id."""
    return asdict(store.complete(task_id))


@mcp.resource("tasks://summary")
def task_summary() -> str:
    """Read-only overview for clients that attach context without calling a tool."""
    done = sum(t.done for t in store.tasks.values())
    return f"{len(store.tasks)} tasks, {done} done"


if __name__ == "__main__":
    mcp.run(transport="stdio")
