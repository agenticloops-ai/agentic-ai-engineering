"""
Hooks & Lifecycle (Anthropic)

Demonstrates a dependency-free hook registry that intercepts the agent loop at its seams:

- pre_tool_use: allow, deny, or replace a tool call before it runs
- post_tool_use: observe or rewrite a tool result before the model sees it
- stop: let the agent finish, or send it back to work with feedback

Logging, guardrails, and approval gates become pluggable callbacks, so the loop itself never
has to change. A scripted dry run shows every decision without an API key.
"""

import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
EFFORT = "medium"
MAX_ITERATIONS = 15
MAX_STOP_BLOCKS = 2

# Re-run a safety-declined turn on a fallback model instead of ending the loop
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """You are a coding agent working inside a project workspace.

Guidelines:
- Use relative paths; the workspace is your working directory
- When a tool call is denied, do not work around it: continue without it and report it
- When done, give a brief summary of what you accomplished"""

TOOLS: list[Any] = [
    {
        "name": "write_file",
        "description": "Write content to a file, creating parent folders as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path to read"}},
            "required": ["path"],
        },
    },
    {
        "name": "bash",
        "description": "Run a shell command in the workspace and return its output.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Command to run"}},
            "required": ["command"],
        },
    },
]

BLOCKED_COMMAND_PATTERNS = [
    r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\*)",
    r"\bsudo\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\s*\{",
    r"\bcurl\b[^|]*\|\s*(ba)?sh",
]
APPROVAL_COMMAND_PATTERNS = [r"\bpip3?\s+install\b", r"\bgit\s+push\b", r"\bnpm\s+publish\b"]
SECRET_PATTERN = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{8,})\b")


class HookEvent(StrEnum):
    """The lifecycle points where the loop hands control to hooks."""

    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    STOP = "stop"


@dataclass(frozen=True)
class PreToolDecision:
    """What a pre_tool_use hook wants done with a call; hooks may also return None for allow."""

    action: Literal["allow", "deny", "replace"] = "allow"
    reason: str = ""
    tool_input: dict[str, Any] | None = None


@dataclass(frozen=True)
class PreToolOutcome:
    """The combined verdict of every pre_tool_use hook."""

    allowed: bool
    tool_input: dict[str, Any]
    reason: str = ""


def deny(reason: str) -> PreToolDecision:
    """Refuse the tool call; the reason goes back to the model as a tool error."""
    return PreToolDecision(action="deny", reason=reason)


def replace(tool_input: dict[str, Any], reason: str = "") -> PreToolDecision:
    """Run the tool with different arguments than the model asked for."""
    return PreToolDecision(action="replace", reason=reason, tool_input=tool_input)


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
        """Return the hooks for an event, in registration order."""
        return [hook for matcher, hook in self._hooks[event] if matcher in (None, tool)]

    def run_pre_tool(self, tool: str, tool_input: dict[str, Any]) -> PreToolOutcome:
        """Chain pre_tool_use hooks: a deny stops the chain, a replace feeds the next hook."""
        current = tool_input
        for hook in self._matching(HookEvent.PRE_TOOL_USE, tool):
            try:
                decision = hook(tool, current)
            except Exception as e:
                # Fail closed: a crashed guardrail must not turn into a silent allow
                logger.error(f"pre_tool_use hook {hook.__name__} failed: {e}")
                return PreToolOutcome(False, current, f"Hook {hook.__name__} failed; call denied")
            if decision is None or decision.action == "allow":
                continue
            if decision.action == "deny":
                return PreToolOutcome(False, current, decision.reason)
            current = decision.tool_input or current
            logger.info(f"✏️  {hook.__name__} replaced input: {decision.reason}")
        return PreToolOutcome(True, current)

    def run_post_tool(self, tool: str, tool_input: dict[str, Any], result: str) -> str:
        """Chain post_tool_use hooks: returning a string rewrites the result."""
        current = result
        for hook in self._matching(HookEvent.POST_TOOL_USE, tool):
            try:
                rewritten = hook(tool, tool_input, current)
                current = rewritten if rewritten is not None else current
            except Exception as e:
                # Fail open: the tool already ran, so losing an observer shouldn't lose the result
                logger.error(f"post_tool_use hook {hook.__name__} failed: {e}")
        return current

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


class ToolExecutor:
    """Runs tools in a workspace folder. Note this is containment by convention, not a sandbox."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def execute(self, name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool and return its output as a string."""
        if name == "write_file":
            path = self.workspace / tool_input["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(tool_input["content"])
            return f"Wrote {len(tool_input['content'])} characters to {tool_input['path']}"
        if name == "read_file":
            return Path(self.workspace, tool_input["path"]).read_text()
        if name == "bash":
            result = subprocess.run(
                tool_input["command"],
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return (result.stdout + result.stderr) or f"(no output, exit {result.returncode})"
        raise ValueError(f"Unknown tool: {name}")


@dataclass
class AuditLog:
    """Records every decision so a run can be reconstructed afterwards."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, tool: str, outcome: str, detail: str = "", duration_ms: float = 0.0) -> None:
        """Append one audit entry."""
        self.entries.append(
            {"tool": tool, "outcome": outcome, "detail": detail, "duration_ms": duration_ms}
        )


def register_builtin_hooks(
    hooks: HookRegistry,
    audit: AuditLog,
    workspace: Path,
    approve: Callable[[str], bool],
) -> None:
    """Wire up the module's guardrails; each one is independent and removable."""
    started: dict[str, float] = {}

    @hooks.on(HookEvent.PRE_TOOL_USE, tool="bash")
    def block_dangerous_commands(_tool: str, tool_input: dict[str, Any]) -> PreToolDecision | None:
        """The BLOCKED_COMMANDS guardrail from earlier tutorials, now as a removable hook."""
        command = tool_input.get("command", "")
        for pattern in BLOCKED_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return deny(f"Blocked: command matches dangerous pattern {pattern!r}")
        return None

    @hooks.on(HookEvent.PRE_TOOL_USE, tool="bash")
    def require_approval(_tool: str, tool_input: dict[str, Any]) -> PreToolDecision | None:
        """Pause for a human before commands with effects outside the workspace."""
        command = tool_input.get("command", "")
        needs_approval = any(re.search(p, command) for p in APPROVAL_COMMAND_PATTERNS)
        if needs_approval and not approve(command):
            return deny("A human reviewer rejected this command. Do not retry it.")
        return None

    @hooks.on(HookEvent.PRE_TOOL_USE, tool="write_file")
    @hooks.on(HookEvent.PRE_TOOL_USE, tool="read_file")
    def confine_to_workspace(_tool: str, tool_input: dict[str, Any]) -> PreToolDecision | None:
        """Redirect any path that leaves the workspace to the same filename inside it."""
        root = workspace.resolve()
        requested = tool_input.get("path", "")
        if (root / requested).resolve().is_relative_to(root):
            return None
        safe_path = Path(requested).name
        return replace({**tool_input, "path": safe_path}, f"{requested} → {safe_path}")

    @hooks.on(HookEvent.PRE_TOOL_USE)
    def start_timer(tool: str, _tool_input: dict[str, Any]) -> None:
        """Runs last, so only calls that passed every guardrail get timed."""
        started[tool] = time.perf_counter()

    @hooks.on(HookEvent.POST_TOOL_USE)
    def redact_secrets(_tool: str, _tool_input: dict[str, Any], result: str) -> str | None:
        """Keep secrets found in tool output out of the conversation history."""
        redacted, count = SECRET_PATTERN.subn("[REDACTED]", result)
        if count:
            logger.warning(f"🔒 Redacted {count} secret(s) from tool output")
            return redacted
        return None

    @hooks.on(HookEvent.POST_TOOL_USE)
    def audit_tool_call(tool: str, tool_input: dict[str, Any], result: str) -> None:
        """Record what ran, on what input, and how long it took."""
        elapsed = (time.perf_counter() - started.pop(tool, time.perf_counter())) * 1000
        audit.record(tool, "ran", json.dumps(tool_input)[:80], elapsed)
        logger.info(f"📋 {tool} → {result[:80]!r}")


def register_verification_hook(hooks: HookRegistry) -> None:
    """Add a stop hook that refuses to end the task until written Python code has been run."""
    state = {"unverified": False}

    @hooks.on(HookEvent.POST_TOOL_USE, tool="write_file")
    def mark_unverified(_tool: str, tool_input: dict[str, Any], _result: str) -> None:
        if str(tool_input.get("path", "")).endswith(".py"):
            state["unverified"] = True

    @hooks.on(HookEvent.POST_TOOL_USE, tool="bash")
    def mark_verified(_tool: str, tool_input: dict[str, Any], _result: str) -> None:
        if re.search(r"\b(pytest|unittest|python3?\s)", tool_input.get("command", "")):
            state["unverified"] = False

    @hooks.on(HookEvent.STOP)
    def require_verification(_final_text: str) -> str | None:
        if state["unverified"]:
            return "You wrote Python code but never ran it. Run it, fix any failure, then finish."
        return None


class HookedAgent:
    """The agent loop from Foundations, with hooks at each of its seams."""

    def __init__(self, hooks: HookRegistry, executor: ToolExecutor, audit: AuditLog) -> None:
        self.client = anthropic.Anthropic()
        self.hooks = hooks
        self.executor = executor
        self.audit = audit
        self.token_tracker = AnthropicTokenTracker()

    def run_tool_call(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Pass one tool call through pre hooks, execution, and post hooks."""
        outcome = self.hooks.run_pre_tool(name, tool_input)
        if not outcome.allowed:
            logger.warning(f"🛑 {name} denied: {outcome.reason}")
            self.audit.record(name, "denied", outcome.reason)
            return f"Denied: {outcome.reason}", True
        try:
            result = self.executor.execute(name, outcome.tool_input)
            is_error = False
        except Exception as e:
            result = f"Error: {e}"
            is_error = True
        return self.hooks.run_post_tool(name, outcome.tool_input, result), is_error

    def run(self, task: str) -> str:
        """Execute the agent loop for one task."""
        messages: list[Any] = [{"role": "user", "content": task}]
        stop_blocks = 0

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"--- Iteration {iteration + 1} ---")
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                output_config={"effort": EFFORT},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            self.token_tracker.track(response.usage)
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                text = "\n".join(b.text for b in response.content if b.type == "text")
                # A cap on stop blocks means a stubborn hook can't trap the agent forever
                feedback = self.hooks.run_stop(text) if stop_blocks < MAX_STOP_BLOCKS else None
                if feedback and response.stop_reason == "end_turn":
                    stop_blocks += 1
                    logger.info(f"🔁 Stop hook sent the agent back: {feedback}")
                    messages.append({"role": "user", "content": feedback})
                    continue
                return text or f"(no text returned, stop_reason={response.stop_reason})"

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    content, is_error = self.run_tool_call(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                            "is_error": is_error,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

        return "Stopped: reached the iteration limit before finishing."


def run_scripted_dry_run(console: Console) -> None:
    """Fire tool calls through the real hooks with no LLM, showing each decision."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        audit = AuditLog()
        hooks = HookRegistry()
        # Reject everything: this dry run must never install or push anything for real
        register_builtin_hooks(hooks, audit, workspace, approve=lambda _command: False)

        calls: list[tuple[str, dict[str, Any], str]] = [
            ("bash", {"command": "echo hello"}, "A harmless command passes through"),
            ("bash", {"command": "sudo rm -rf /"}, "A guardrail denies it"),
            ("bash", {"command": "pip install requests"}, "The approval gate denies it"),
            ("write_file", {"path": "/etc/app.conf", "content": "x"}, "The path gets rewritten"),
            ("read_file", {"path": "app.conf"}, "It landed inside the workspace"),
            ("bash", {"command": "echo key=sk-abc12345678"}, "The secret is redacted"),
        ]

        executor = ToolExecutor(workspace)
        table = Table(title="Scripted dry run (no LLM)")
        table.add_column("Tool call")
        table.add_column("Expected")
        table.add_column("Tool result")
        for name, tool_input, expected in calls:
            outcome = hooks.run_pre_tool(name, tool_input)
            if not outcome.allowed:
                result = f"[red]{escape(outcome.reason)}[/red]"
            else:
                output = executor.execute(name, outcome.tool_input)
                result = escape(hooks.run_post_tool(name, outcome.tool_input, output))
            shown = tool_input.get("command") or f"{name} {tool_input['path']}"
            table.add_row(escape(shown), expected, result)
        console.print(table)


def ask_for_approval(command: str) -> bool:
    """Ask the human running the script whether a risky command may run."""
    Console().print(f"\n[bold yellow]Approve command?[/bold yellow] {command} [y/N] ", end="")
    return input().strip().lower() == "y"


def main() -> None:
    """Main orchestration function."""
    console = Console()
    run_scripted_dry_run(console)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("\n[yellow]Set ANTHROPIC_API_KEY to run the live agent.[/yellow]")
        return

    tasks = [
        "Create slug.py with a slugify(text) function and test_slug.py with a few assertions.",
        "Run `sudo whoami` and tell me what happened.",
        "Install the 'requests' package with pip, then write /etc/hooks_demo.txt saying hello.",
    ]
    examples = "\n".join(f"  {i}. {task}" for i, task in enumerate(tasks, 1))
    console.print(
        Panel(
            f"Pick an example or type your own task:\n{examples}\n\nType 'quit' to exit.",
            title="Hooked Agent (Anthropic)",
        )
    )

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        audit = AuditLog()
        hooks = HookRegistry()
        register_builtin_hooks(hooks, audit, workspace, approve=ask_for_approval)
        register_verification_hook(hooks)
        agent = HookedAgent(hooks, ToolExecutor(workspace), audit)

        try:
            while True:
                console.print("\n[bold green]You:[/bold green] ", end="")
                user_input = input().strip()
                if user_input.lower() in ("exit", "quit", "q", ""):
                    break
                if user_input.isdigit() and 1 <= int(user_input) <= len(tasks):
                    user_input = tasks[int(user_input) - 1]

                answer = agent.run(user_input)
                console.print("\n[bold blue]Agent:[/bold blue]")
                console.print(Markdown(answer))
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Interrupted.[/yellow]")
        except anthropic.APIError as e:
            logger.error(f"API error: {e}")

        audit_table = Table(title="Audit log")
        for column in ("Tool", "Outcome", "Detail", "ms"):
            audit_table.add_column(column)
        for entry in audit.entries:
            audit_table.add_row(
                entry["tool"],
                entry["outcome"],
                escape(entry["detail"]),
                f"{entry['duration_ms']:.0f}",
            )
        console.print(audit_table)

    agent.token_tracker.report()


if __name__ == "__main__":
    main()
