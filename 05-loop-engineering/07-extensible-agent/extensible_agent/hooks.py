"""Layer: hooks. Control points around tool calls and around the agent's decision to stop."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from common import setup_logging

logger = setup_logging(__name__)


class HookEvent(StrEnum):
    """The lifecycle points where the loop hands control to hooks."""

    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    STOP = "stop"


@dataclass(frozen=True)
class Deny:
    """Returned by a pre_tool_use hook to refuse a call; the reason goes to the model."""

    reason: str


@dataclass
class HookRegistry:
    """Maps lifecycle events to callables, with an optional tool-name matcher."""

    _hooks: dict[HookEvent, list[tuple[str | None, Callable[..., Any]]]] = field(
        default_factory=lambda: {event: [] for event in HookEvent}
    )

    def on(self, event: HookEvent, tool: str | None = None) -> Callable[..., Any]:
        """Decorator that registers a hook, optionally only for one tool."""

        def register(hook: Callable[..., Any]) -> Callable[..., Any]:
            self._hooks[event].append((tool, hook))
            return hook

        return register

    def _matching(self, event: HookEvent, tool: str | None) -> list[Callable[..., Any]]:
        return [hook for matcher, hook in self._hooks[event] if matcher in (None, tool)]

    def run_pre_tool(self, tool: str, tool_input: dict[str, Any]) -> str | None:
        """Return a denial reason, or None if every hook allows the call. Fails closed."""
        for hook in self._matching(HookEvent.PRE_TOOL_USE, tool):
            try:
                decision = hook(tool, tool_input)
            except Exception as e:
                logger.error(f"pre_tool_use hook {hook.__name__} failed: {e}")
                return f"Hook {hook.__name__} failed; call denied"
            if isinstance(decision, Deny):
                return decision.reason
        return None

    def run_post_tool(self, tool: str, tool_input: dict[str, Any], result: str) -> str:
        """Chain post_tool_use hooks: returning a string rewrites the result. Fails open."""
        for hook in self._matching(HookEvent.POST_TOOL_USE, tool):
            try:
                rewritten = hook(tool, tool_input, result)
                result = rewritten if rewritten is not None else result
            except Exception as e:
                logger.error(f"post_tool_use hook {hook.__name__} failed: {e}")
        return result

    def run_stop(self, final_text: str) -> str | None:
        """Return feedback from the first stop hook that objects, or None to let the agent end."""
        for hook in self._matching(HookEvent.STOP, None):
            try:
                feedback = hook(final_text)
            except Exception as e:
                logger.error(f"stop hook {hook.__name__} failed: {e}")
                continue
            if feedback:
                return str(feedback)
        return None
