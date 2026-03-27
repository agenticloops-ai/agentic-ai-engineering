"""
Tool-use agent with dependency injection for testability.

Encapsulates the core agent loop: send message to LLM, parse tool calls,
execute tools, send results back, repeat until text response or max iterations.
"""

import json
from typing import Any

from common import AnthropicTokenTracker, setup_logging

from shared.tools import TOOLS, execute_tool

logger = setup_logging(__name__)


class ToolUseAgent:
    """Tool-use agent with dependency injection and iteration limits."""

    def __init__(
        self,
        client: Any,
        model: str = "claude-sonnet-4-5-20250929",
        max_iterations: int = 10,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.max_iterations = max_iterations
        self.tools = tools if tools is not None else TOOLS
        self.messages: list[dict[str, Any]] = []
        self.token_tracker = AnthropicTokenTracker()

    def send_message(self, user_message: str) -> str:
        """Send a message and process the agent loop until a text response."""
        self.messages.append({"role": "user", "content": user_message})
        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1
            logger.info(
                "Iteration %d/%d (messages: %d)",
                iterations,
                self.max_iterations,
                len(self.messages),
            )

            # KEY CONCEPT: The injected client is called here — easy to mock
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=self.tools,
                messages=self.messages,
            )

            self.token_tracker.track(response.usage)

            tool_uses = []
            text_content = []

            for block in response.content:
                if hasattr(block, "text"):
                    text_content.append(block.text)
                elif hasattr(block, "name") and hasattr(block, "input"):
                    tool_uses.append(block)

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use" or not tool_uses:
                return "\n".join(text_content) if text_content else ""

            # Execute each tool and send results back
            tool_results = []
            for tool_use in tool_uses:
                result = execute_tool(tool_use.name, tool_use.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result),
                    }
                )

            self.messages.append({"role": "user", "content": tool_results})

        # CONTRACT: max_iterations reached — agent must stop
        logger.warning("Max iterations (%d) reached, stopping agent", self.max_iterations)
        return "[Agent stopped: maximum iterations reached]"
