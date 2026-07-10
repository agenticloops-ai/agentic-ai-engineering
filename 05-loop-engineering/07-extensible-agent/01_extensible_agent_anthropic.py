"""
Extensible Agent — Capstone (Anthropic)

One agent, every primitive from this module wired together:

  - Hooks         guard and log every tool call (02-hooks-lifecycle)
  - Sandbox       run_python executes in a resource-limited subprocess (03-sandboxing)
  - MCP           extra tools are discovered from an MCP server at runtime (04-mcp)
  - Subagents     spawn_subagent delegates subtasks with isolated context (05-subagents)
  - Compaction    the loop summarizes its own history past a budget (06-context-compaction)

The point isn't new capability — it's that each layer stays independent and
composable. Shared building blocks live in components.py; the MCP server is
mcp_server.py.
"""

import asyncio
import json
import sys
from typing import Any

import anthropic
from anthropic.types import TextBlock, ToolUseBlock
from components import (
    POST_TOOL_USE,
    PRE_TOOL_USE,
    STOP,
    HookRegistry,
    block_risky_code,
    estimate_tokens,
    run_in_subprocess,
)
from dotenv import find_dotenv, load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import AnthropicTokenTracker

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

COMPACT_TOKEN_BUDGET = 4000
MAX_SUBAGENTS = 3
SERVER = StdioServerParameters(command=sys.executable, args=["mcp_server.py"])

SYSTEM_PROMPT = """You are an extensible agent. You can run Python (run_python,
sandboxed), delegate subtasks (spawn_subagent), and use tools discovered from an
MCP server. Break big tasks down, delegate independent parts, and summarize."""

WORKER_PROMPT = """You are a worker with the role: {role}. Complete the subtask
using run_python and return a concise summary."""

RUN_PYTHON_TOOL = {
    "name": "run_python",
    "description": "Run a self-contained Python snippet in a sandbox; returns stdout/stderr.",
    "input_schema": {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python source to execute"}},
        "required": ["code"],
    },
}
SPAWN_TOOL = {
    "name": "spawn_subagent",
    "description": "Delegate a subtask to a fresh subagent with isolated context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "The subtask to delegate"},
            "role": {"type": "string", "description": "The subagent's role"},
        },
        "required": ["task", "role"],
    },
}


def to_anthropic_tools(mcp_tools: Any) -> list[dict[str, Any]]:
    """Bridge MCP tool definitions into Anthropic's tool schema."""
    return [
        {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
        for t in mcp_tools
    ]


def extract_text(result: Any) -> str:
    """Flatten an MCP call_tool result into a plain string."""
    parts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    text = "\n".join(parts) if parts else "(no output)"
    return f"Error: {text}" if result.isError else text


class ExtensibleAgent:
    """Capstone agent composing hooks, sandbox, MCP, subagents, and compaction."""

    def __init__(self, hooks: HookRegistry, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_iterations = 20
        self.token_tracker = AnthropicTokenTracker()
        self.hooks = hooks
        self.subagent_count = 0
        self.compactions = 0

    def _run_python_guarded(self, tool_input: dict[str, Any]) -> str:
        """Run the sandbox tool through the hook pipeline (used by parent and workers)."""
        decision = self.hooks.run_pre_tool_use("run_python", tool_input)
        if not decision.allow:
            logger.warning(f"⛔ Denied run_python: {decision.reason}")
            return f"Tool call denied by policy: {decision.reason}"
        ti = decision.tool_input or tool_input
        result = run_in_subprocess(ti["code"])
        self.hooks.run_post_tool_use("run_python", ti, result)
        return result

    async def _dispatch(self, session: ClientSession, mcp_names: set[str], block: Any) -> str:
        """Route one tool call: sandbox, subagent, or MCP — all through hooks."""
        name, tool_input = block.name, dict(block.input)
        if name == "run_python":
            return self._run_python_guarded(tool_input)
        if name == "spawn_subagent":
            return self._spawn_subagent(tool_input["task"], tool_input["role"])
        if name in mcp_names:
            decision = self.hooks.run_pre_tool_use(name, tool_input)
            if not decision.allow:
                return f"Tool call denied by policy: {decision.reason}"
            call = await session.call_tool(name, decision.tool_input or tool_input)
            result = extract_text(call)
            self.hooks.run_post_tool_use(name, tool_input, result)
            return result
        return f"Unknown tool: {name}"

    def _spawn_subagent(self, task: str, role: str) -> str:
        """Run a fresh, sandbox-only worker to completion and return its summary."""
        if self.subagent_count >= MAX_SUBAGENTS:
            return f"Error: subagent limit ({MAX_SUBAGENTS}) reached"
        self.subagent_count += 1
        logger.info(f"🧑‍🚀 Subagent #{self.subagent_count} [{role}]: {task[:80]}")

        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        for _ in range(self.max_iterations):
            response = self.client.messages.create(
                model=self.model,
                temperature=0.1,
                max_tokens=2048,
                system=WORKER_PROMPT.format(role=role),
                tools=[RUN_PYTHON_TOOL],
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            assistant_content: list[dict[str, Any]] = []
            for b in response.content:
                if isinstance(b, TextBlock):
                    assistant_content.append({"type": "text", "text": b.text})
                elif isinstance(b, ToolUseBlock):
                    assistant_content.append(
                        {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                    )
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                return response.content[0].text if response.content else "(no summary)"

            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": self._run_python_guarded(dict(b.input)),
                }
                for b in response.content
                if isinstance(b, ToolUseBlock)
            ]
            messages.append({"role": "user", "content": results})
        return "(subagent hit iteration limit)"

    def _compact(self, task: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Summarize and rebuild history at a turn boundary (no split tool pairs)."""
        self.compactions += 1
        transcript = json.dumps(messages, default=str, indent=2)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system="Summarize this agent transcript: goal, decisions, findings, what remains.",
            messages=[{"role": "user", "content": f"Goal: {task}\n\n{transcript}"}],
        )
        self.token_tracker.track(response.usage)
        summary = response.content[0].text if response.content else ""
        logger.info(f"🗜️  Compaction #{self.compactions}: {len(messages)} msgs -> 1")
        return [{"role": "user", "content": f"{task}\n\n[Progress]:\n{summary}\n\nContinue."}]

    async def run(
        self, session: ClientSession, tools: list[dict[str, Any]], mcp_names: set[str], task: str
    ) -> str:
        """Execute the capstone loop with all layers active."""
        logger.info(f"Task: {task}")
        self.subagent_count = 0
        self.compactions = 0
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

        for iteration in range(self.max_iterations):
            if len(messages) > 2 and estimate_tokens(messages) > COMPACT_TOKEN_BUDGET:
                messages = self._compact(task, messages)

            logger.info(f"--- Iteration {iteration + 1} (~{estimate_tokens(messages)} tok) ---")
            response = self.client.messages.create(
                model=self.model,
                temperature=0.1,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            assistant_content: list[dict[str, Any]] = []
            for b in response.content:
                if isinstance(b, TextBlock):
                    logger.info(f"🤖 Agent: {b.text}")
                    assistant_content.append({"type": "text", "text": b.text})
                elif isinstance(b, ToolUseBlock):
                    logger.info(f"🔧 {b.name}")
                    assistant_content.append(
                        {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                    )
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                final = response.content[0].text if response.content else "Done"
                self.hooks.run_stop(final)
                return final

            tool_results = []
            for b in response.content:
                if isinstance(b, ToolUseBlock):
                    result = await self._dispatch(session, mcp_names, b)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": b.id, "content": result}
                    )
            messages.append({"role": "user", "content": tool_results})

        return "Max iterations reached"


def build_registry() -> HookRegistry:
    """Wire the built-in logging and code-guardrail hooks."""
    registry = HookRegistry()
    registry.register(PRE_TOOL_USE, lambda n, i: logger.info(f"🪝 pre: {n}") or None)
    registry.register(PRE_TOOL_USE, block_risky_code)
    registry.register(POST_TOOL_USE, lambda n, i, r: logger.info(f"🪝 post: {n} -> {len(r)} chars"))
    registry.register(STOP, lambda final: logger.info("🪝 stop: loop finished"))
    return registry


async def main_async() -> None:
    """Open the MCP session, wire all layers, and run the interactive loop."""
    console = Console()
    agent = ExtensibleAgent(build_registry())

    async with stdio_client(SERVER) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listing = await session.list_tools()
        mcp_tools = to_anthropic_tools(listing.tools)
        mcp_names = {t["name"] for t in mcp_tools}
        tools = [RUN_PYTHON_TOOL, SPAWN_TOOL, *mcp_tools]

        console.print(
            Panel(
                "Extensible agent: hooks + sandbox + MCP + subagents + compaction.\n\n"
                f"MCP tools: {', '.join(mcp_names)}\n\n"
                "Try:\n"
                "  - Use subagents to compute 12! and the prime factors of 360\n"
                "  - Try to open a network socket in run_python (watch the guardrail)\n\n"
                "Type 'quit' to exit.",
                title="Extensible Agent — Capstone (Anthropic)",
            )
        )

        try:
            while True:
                console.print("\n[bold green]You:[/bold green] ", end="")
                user_input = input().strip()
                if user_input.lower() in ("exit", "quit", "q", ""):
                    console.print("\n[yellow]Ending session...[/yellow]")
                    break
                response = await agent.run(session, tools, mcp_names, user_input)
                console.print(
                    f"\n[dim]subagents={agent.subagent_count} compactions={agent.compactions}[/dim]"
                )
                console.print("\n[bold blue]Agent:[/bold blue]")
                console.print(Markdown(response))
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    agent.token_tracker.report()


def main() -> None:
    """Entry point wrapping the async MCP session."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
