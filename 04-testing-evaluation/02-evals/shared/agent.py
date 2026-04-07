"""
Research assistant agent for evaluation tutorials.

Implements a tool-use agent that searches a knowledge base and synthesizes
answers with source citations. Used as the system under test in eval pipelines.
"""

import json
from typing import Any

import anthropic
from common import AnthropicTokenTracker, setup_logging

from shared.knowledge_base import KNOWLEDGE_BASE, SYSTEM_PROMPT, TOOLS, search_knowledge_base

logger = setup_logging(__name__)


class ResearchAssistant:
    """Research assistant that searches a knowledge base and synthesizes answers."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        knowledge_base: list[dict[str, Any]] | None = None,
        model: str = "claude-sonnet-4-5-20250929",
    ) -> None:
        self.client = client
        self.knowledge_base = knowledge_base if knowledge_base is not None else KNOWLEDGE_BASE
        self.model = model
        self.token_tracker = AnthropicTokenTracker()

    def answer(self, question: str) -> dict[str, Any]:
        """Answer a question using the knowledge base."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        tool_calls_made: list[dict[str, Any]] = []

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            if response.stop_reason != "tool_use":
                answer_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        answer_text += block.text
                return {
                    "answer": answer_text,
                    "tool_calls": tool_calls_made,
                    "sources": [tc["results"] for tc in tool_calls_made],
                }

            # Process tool calls
            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = search_knowledge_base(**block.input, corpus=self.knowledge_base)
                    tool_calls_made.append(
                        {"name": block.name, "input": block.input, "results": result}
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
