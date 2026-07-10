"""
Reusable loop-engineering components for the capstone.

Each piece is the distilled version of one earlier tutorial, kept provider-agnostic
so both capstone scripts wire the same building blocks:

  - HookRegistry / HookDecision  (02-hooks-lifecycle)
  - run_in_subprocess sandbox    (03-sandboxing)
  - estimate_tokens              (06-context-compaction)
"""

import json
import resource
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PRE_TOOL_USE = "pre_tool_use"
POST_TOOL_USE = "post_tool_use"
STOP = "stop"

CPU_SECONDS = 5
MEMORY_BYTES = 512 * 1024 * 1024
WALL_TIMEOUT = 10
RISKY_TOKENS = ["socket", "subprocess", "urllib", "requests", "os.system"]


@dataclass
class HookDecision:
    """Verdict a pre_tool_use hook returns. Deny blocks the call; tool_input rewrites it."""

    allow: bool = True
    reason: str = ""
    tool_input: dict[str, Any] | None = None


@dataclass
class HookRegistry:
    """Maps lifecycle events to ordered lists of callbacks."""

    hooks: dict[str, list[Callable[..., Any]]] = field(
        default_factory=lambda: {PRE_TOOL_USE: [], POST_TOOL_USE: [], STOP: []}
    )

    def register(self, event: str, fn: Callable[..., Any]) -> None:
        """Attach a callback to a lifecycle event."""
        self.hooks[event].append(fn)

    def run_pre_tool_use(self, name: str, tool_input: dict[str, Any]) -> HookDecision:
        """Run pre-tool hooks; first denial wins, rewrites chain through."""
        for fn in self.hooks[PRE_TOOL_USE]:
            decision = fn(name, tool_input)
            if decision is None:
                continue
            if not decision.allow:
                return decision
            if decision.tool_input is not None:
                tool_input = decision.tool_input
        return HookDecision(allow=True, tool_input=tool_input)

    def run_post_tool_use(self, name: str, tool_input: dict[str, Any], result: str) -> None:
        """Run observation hooks after a tool executes."""
        for fn in self.hooks[POST_TOOL_USE]:
            fn(name, tool_input, result)

    def run_stop(self, final: str) -> None:
        """Run hooks once the loop is done."""
        for fn in self.hooks[STOP]:
            fn(final)


def block_risky_code(name: str, tool_input: dict[str, Any]) -> HookDecision | None:
    """Guardrail hook: deny sandboxed code that reaches for the network or the host."""
    if name != "run_python":
        return None
    code = tool_input.get("code", "")
    for token in RISKY_TOKENS:
        if token in code:
            return HookDecision(allow=False, reason=f"risky token '{token}'")
    return None


def _apply_limits() -> None:
    """Cap CPU and address space for the sandboxed child (POSIX only)."""
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))


def run_in_subprocess(code: str) -> str:
    """Run Python code in a resource-limited subprocess with a stripped environment."""
    with tempfile.TemporaryDirectory(prefix="sandbox_") as tmp:
        script = Path(tmp) / "snippet.py"
        script.write_text(code)
        try:
            proc = subprocess.run(
                ["python", "-I", str(script)],
                cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "HOME": tmp, "LANG": "C.UTF-8"},
                capture_output=True,
                text=True,
                timeout=WALL_TIMEOUT,
                preexec_fn=_apply_limits,
            )
        except subprocess.TimeoutExpired:
            return f"Timed out after {WALL_TIMEOUT}s"
        out = (proc.stdout + proc.stderr) or "(no output)"
        return f"exit={proc.returncode}\n{out}"


def estimate_tokens(items: list[Any]) -> int:
    """Rough token estimate (~4 chars/token) over a serialized message/input list."""
    return len(json.dumps(items, default=str)) // 4
