"""
The loop at the center. It knows about tools, hooks, and compaction through narrow interfaces, and
nothing about skills, sandboxes, MCP, or subagents: those arrive as ordinary Tools.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import anthropic

from common import AnthropicTokenTracker, setup_logging
from extensible_agent.compaction import Compactor
from extensible_agent.hooks import HookRegistry
from extensible_agent.tools import ToolSet

logger = setup_logging(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
MAX_ITERATIONS = 25
MAX_STOP_BLOCKS = 2

# Re-run a safety-declined turn on a fallback model instead of ending the loop
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class AgentNode:
    """One agent in the tree, with its own token usage."""

    label: str
    tracker: AnthropicTokenTracker = field(default_factory=AnthropicTokenTracker)
    children: list["AgentNode"] = field(default_factory=list)

    def total_tokens(self) -> int:
        """Tokens used by this agent and everything below it."""
        own: int = self.tracker.get_total_tokens()
        return own + sum(c.total_tokens() for c in self.children)


class Agent:
    """Runs one conversation, passing every seam through the layer that owns it."""

    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        node: AgentNode,
        system_prompt: str,
        tools: ToolSet,
        hooks: HookRegistry,
        compactor: Compactor | None = None,
        effort: str = "medium",
        enforce_stop_hooks: bool = True,
    ) -> None:
        self.client = client
        self.node = node
        self.system_prompt = system_prompt
        self.tools = tools
        self.hooks = hooks
        self.compactor = compactor
        self.effort = effort
        self.enforce_stop_hooks = enforce_stop_hooks

    async def _run_tool_call(self, block: Any) -> dict[str, Any]:
        """Pass one call through pre hooks, the tool, and post hooks."""
        logger.info(f"[{self.node.label}] 🔧 {block.name}({json.dumps(block.input)[:120]})")
        denial = self.hooks.run_pre_tool(block.name, block.input)
        if denial:
            logger.warning(f"[{self.node.label}] 🛑 {block.name} denied: {denial}")
            content, is_error = f"Denied: {denial}", True
        else:
            content, is_error = await self.tools.call(block.name, block.input)
            content = self.hooks.run_post_tool(block.name, block.input, content)
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": content,
            "is_error": is_error,
        }

    async def run(self, task: str) -> str:
        """Execute the loop until the agent finishes and the stop hooks agree."""
        messages: list[Any] = [{"role": "user", "content": task}]
        stop_blocks = 0

        for iteration in range(1, MAX_ITERATIONS + 1):
            logger.info(f"[{self.node.label}] iteration {iteration}")
            response = await self.client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                output_config={"effort": self.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=self.system_prompt,
                tools=self.tools.schemas,
                messages=messages,
            )
            self.node.tracker.track(response.usage)
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                text = "\n".join(b.text for b in response.content if b.type == "text")
                if self.enforce_stop_hooks and response.stop_reason == "end_turn":
                    feedback = self.hooks.run_stop(text) if stop_blocks < MAX_STOP_BLOCKS else None
                    if feedback:
                        stop_blocks += 1
                        logger.info(f"🔁 Stop hook sent the agent back: {feedback}")
                        messages.append({"role": "user", "content": feedback})
                        continue
                return text or f"(no text returned, stop_reason={response.stop_reason})"

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            # Concurrent, so parallel subagents really do run at once; one message of results
            results = await asyncio.gather(*(self._run_tool_call(b) for b in tool_uses))
            messages.append({"role": "user", "content": list(results)})

            # A round boundary: every tool_use has its result, so it's safe to compact
            if self.compactor and self.compactor.should_compact(response.usage):
                compacted = await self.compactor.compact(
                    self.node.label, task, messages, self.node.tracker
                )
                messages = compacted or messages

        return "Stopped: reached the iteration limit before finishing."
