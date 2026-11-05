"""Layer: delegation. A tool that runs a whole child agent and returns only its summary."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import anthropic

from common import setup_logging
from extensible_agent.agent import Agent, AgentNode
from extensible_agent.tools import Tool, ToolOutput

logger = setup_logging(__name__)

MAX_SUMMARY_CHARS = 2_000


@dataclass(frozen=True)
class DelegationLimits:
    """Bounds on the agent tree, because each child costs real money."""

    max_concurrent: int = 4
    max_total_agents: int = 8


class DelegationLayer:
    """Exposes spawn_subagent to the parent; children are built without it, capping depth at 1."""

    def __init__(
        self,
        parent: AgentNode,
        build_child: Callable[[AgentNode], Agent],
        limits: DelegationLimits | None = None,
    ) -> None:
        self.parent = parent
        self.build_child = build_child
        self.limits = limits or DelegationLimits()
        self.semaphore = asyncio.Semaphore(self.limits.max_concurrent)
        self.spawned = 0

    async def _spawn(self, tool_input: dict[str, Any]) -> ToolOutput:
        # Counted before the first await: asyncio can't interleave between check and increment
        if self.spawned >= self.limits.max_total_agents:
            return "Refused: the subagent budget is used up. Finish with what you have.", True
        self.spawned += 1

        node = AgentNode(label=f"{self.parent.label}.{self.spawned}")
        self.parent.children.append(node)
        task = tool_input["task"]
        logger.info(f"🌱 Spawning {node.label}: {task[:80]}")

        async with self.semaphore:
            try:
                summary = await self.build_child(node).run(task)
            except anthropic.APIError as e:
                logger.error(f"[{node.label}] failed: {e}")
                return f"Subagent failed: {e}", True

        logger.info(f"✅ {node.label} done: {node.tracker.get_total_tokens():,} tokens")
        if len(summary) > MAX_SUMMARY_CHARS:
            summary = f"{summary[:MAX_SUMMARY_CHARS]}\n... [summary truncated]"
        return summary, False

    def tools(self) -> list[Tool]:
        """Expose delegation as an ordinary tool."""
        return [
            Tool(
                "spawn_subagent",
                "Delegate a self-contained subtask to a new agent with its own context. Returns "
                "only its final summary. It can't see this conversation, so include everything "
                "it needs. Several can run at once.",
                {
                    "type": "object",
                    "properties": {"task": {"type": "string", "description": "Full instructions"}},
                    "required": ["task"],
                },
                self._spawn,
            )
        ]
