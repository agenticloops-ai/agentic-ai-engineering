"""
Shared traced research assistant agent.

Encapsulates the agent loop with full execution tracing, used by tutorials
that need a live agent (01, 03).
"""

import json
from typing import Any

import anthropic
from common import AnthropicTokenTracker, setup_logging

from shared.knowledge_base import SYSTEM_PROMPT, TOOLS, execute_tool
from shared.tracer import TraceCollector

logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-5-20250929"


class TracedResearchAssistant:
    """Research assistant with full execution tracing."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        tracer: TraceCollector,
    ) -> None:
        self.client = client
        self.tracer = tracer
        self.token_tracker = AnthropicTokenTracker()

    def answer(self, question: str) -> dict[str, Any]:
        """Answer a question with full tracing."""
        with self.tracer.span("answer_question", "agent_step", {"question": question}) as root:
            messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
            llm_call_count = 0

            while True:
                llm_call_count += 1
                with self.tracer.span(
                    f"llm_call_{llm_call_count}",
                    "llm_call",
                    {"message_count": len(messages)},
                ) as llm_span:
                    response = self.client.messages.create(
                        model=MODEL,
                        max_tokens=1024,
                        system=SYSTEM_PROMPT,
                        tools=TOOLS,
                        messages=messages,
                    )
                    self.token_tracker.track(response.usage)
                    llm_span.tokens = {
                        "input": response.usage.input_tokens,
                        "output": response.usage.output_tokens,
                    }
                    llm_span.outputs = {"stop_reason": response.stop_reason}

                # Process response
                tool_uses = []
                text_parts: list[str] = []
                for block in response.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                    elif hasattr(block, "name") and hasattr(block, "input"):
                        tool_uses.append(block)

                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason != "tool_use" or not tool_uses:
                    answer_text = "\n".join(text_parts)
                    root.outputs = {"answer": answer_text[:200], "llm_calls": llm_call_count}
                    return {
                        "answer": answer_text,
                        "llm_calls": llm_call_count,
                        "trace": self.tracer.to_dict(),
                    }

                # Execute tools with tracing
                tool_results = []
                for tool_use in tool_uses:
                    with self.tracer.span(
                        f"tool_{tool_use.name}",
                        "tool_call",
                        {"tool": tool_use.name, "input": tool_use.input},
                    ) as tool_span:
                        result = execute_tool(tool_use.name, tool_use.input)
                        tool_span.outputs = {"result": str(result)[:200]}

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps(result, default=str),
                        }
                    )

                messages.append({"role": "user", "content": tool_results})

                if llm_call_count >= 10:
                    root.error = "Max iterations reached"
                    return {"answer": "Max iterations reached", "llm_calls": llm_call_count}
