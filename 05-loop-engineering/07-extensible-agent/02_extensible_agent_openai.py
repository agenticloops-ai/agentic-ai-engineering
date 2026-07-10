"""
Extensible Agent — Capstone (OpenAI)

The same composition as the Anthropic capstone, driven through the OpenAI Responses
API:

  - Hooks         guard and log every tool call (02-hooks-lifecycle)
  - Sandbox       run_python executes in a resource-limited subprocess (03-sandboxing)
  - MCP           extra tools are discovered from an MCP server at runtime (04-mcp)
  - Subagents     spawn_subagent delegates subtasks with isolated context (05-subagents)
  - Compaction    the loop summarizes its own local input past a budget (06-context-compaction)

Shared building blocks live in components.py; the MCP server is mcp_server.py.
"""

import asyncio
import json
import sys
from typing import Any

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
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import OpenAITokenTracker

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
    "type": "function",
    "name": "run_python",
    "description": "Run a self-contained Python snippet in a sandbox; returns stdout/stderr.",
    "parameters": {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python source to execute"}},
        "additionalProperties": False,
        "required": ["code"],
    },
}
SPAWN_TOOL = {
    "type": "function",
    "name": "spawn_subagent",
    "description": "Delegate a subtask to a fresh subagent with isolated context.",
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "The subtask to delegate"},
            "role": {"type": "string", "description": "The subagent's role"},
        },
        "additionalProperties": False,
        "required": ["task", "role"],
    },
}


def to_openai_tools(mcp_tools: Any) -> list[dict[str, Any]]:
    """Bridge MCP tool definitions into OpenAI's function-tool schema."""
    return [
        {
            "type": "function",
            "name": t.name,
            "description": t.description or "",
            "parameters": t.inputSchema,
        }
        for t in mcp_tools
    ]


def extract_text(result: Any) -> str:
    """Flatten an MCP call_tool result into a plain string."""
    parts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    text = "\n".join(parts) if parts else "(no output)"
    return f"Error: {text}" if result.isError else text


class ExtensibleAgent:
    """Capstone agent composing hooks, sandbox, MCP, subagents, and compaction."""

    def __init__(self, hooks: HookRegistry, model: str = "gpt-4.1"):
        self.client = OpenAI()
        self.model = model
        self.max_iterations = 20
        self.token_tracker = OpenAITokenTracker()
        self.hooks = hooks
        self.subagent_count = 0
        self.compactions = 0

    def _run_python_guarded(self, args: dict[str, Any]) -> str:
        """Run the sandbox tool through the hook pipeline (used by parent and workers)."""
        decision = self.hooks.run_pre_tool_use("run_python", args)
        if not decision.allow:
            logger.warning(f"⛔ Denied run_python: {decision.reason}")
            return f"Tool call denied by policy: {decision.reason}"
        ti = decision.tool_input or args
        result = run_in_subprocess(ti["code"])
        self.hooks.run_post_tool_use("run_python", ti, result)
        return result

    async def _dispatch(
        self, session: ClientSession, mcp_names: set[str], name: str, args: dict[str, Any]
    ) -> str:
        """Route one tool call: sandbox, subagent, or MCP — all through hooks."""
        if name == "run_python":
            return self._run_python_guarded(args)
        if name == "spawn_subagent":
            return self._spawn_subagent(args.get("task", ""), args.get("role", "worker"))
        if name in mcp_names:
            decision = self.hooks.run_pre_tool_use(name, args)
            if not decision.allow:
                return f"Tool call denied by policy: {decision.reason}"
            call = await session.call_tool(name, decision.tool_input or args)
            result = extract_text(call)
            self.hooks.run_post_tool_use(name, args, result)
            return result
        return f"Unknown tool: {name}"

    def _spawn_subagent(self, task: str, role: str) -> str:
        """Run a fresh, sandbox-only worker to completion and return its summary."""
        if self.subagent_count >= MAX_SUBAGENTS:
            return f"Error: subagent limit ({MAX_SUBAGENTS}) reached"
        self.subagent_count += 1
        logger.info(f"🧑‍🚀 Subagent #{self.subagent_count} [{role}]: {task[:80]}")

        input_messages: list[Any] = [{"role": "user", "content": task}]
        previous_response_id: str | None = None
        for _ in range(self.max_iterations):
            response = self.client.responses.create(
                model=self.model,
                tools=[RUN_PYTHON_TOOL],
                instructions=WORKER_PROMPT.format(role=role),
                input=input_messages,
                **({"previous_response_id": previous_response_id} if previous_response_id else {}),
            )
            if response.usage:
                self.token_tracker.track(response.usage)

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                return response.output_text or "(no summary)"

            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"result": self._run_python_guarded(args)}),
                    }
                )
            previous_response_id = response.id
            input_messages = tool_outputs
        return "(subagent hit iteration limit)"

    def _compact(self, task: str, items: list[Any]) -> list[Any]:
        """Summarize and rebuild the local input at a turn boundary."""
        self.compactions += 1
        transcript = json.dumps(items, default=str, indent=2)
        response = self.client.responses.create(
            model=self.model,
            instructions="Summarize this agent transcript: goal, decisions, findings, remaining.",
            input=[{"role": "user", "content": f"Goal: {task}\n\n{transcript}"}],
        )
        if response.usage:
            self.token_tracker.track(response.usage)
        summary = response.output_text or ""
        logger.info(f"🗜️  Compaction #{self.compactions}: {len(items)} items -> 1")
        return [{"role": "user", "content": f"{task}\n\n[Progress]:\n{summary}\n\nContinue."}]

    async def run(
        self, session: ClientSession, tools: list[dict[str, Any]], mcp_names: set[str], task: str
    ) -> str:
        """Execute the capstone loop with all layers active (local input for compaction)."""
        logger.info(f"Task: {task}")
        self.subagent_count = 0
        self.compactions = 0
        input_messages: list[Any] = [{"role": "user", "content": task}]

        for iteration in range(self.max_iterations):
            if len(input_messages) > 2 and estimate_tokens(input_messages) > COMPACT_TOKEN_BUDGET:
                input_messages = self._compact(task, input_messages)

            logger.info(
                f"--- Iteration {iteration + 1} (~{estimate_tokens(input_messages)} tok) ---"
            )
            response = self.client.responses.create(
                model=self.model,
                tools=tools,
                instructions=SYSTEM_PROMPT,
                input=input_messages,
            )
            if response.usage:
                self.token_tracker.track(response.usage)
            if response.output_text:
                logger.info(f"🤖 Agent: {response.output_text}")

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                final = response.output_text or "Done"
                self.hooks.run_stop(final)
                return final

            input_messages += list(response.output)
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError:
                    args = {}
                logger.info(f"🔧 {call.name}")
                result = await self._dispatch(session, mcp_names, call.name, args)
                input_messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"result": result}),
                    }
                )

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
        mcp_tools = to_openai_tools(listing.tools)
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
                title="Extensible Agent — Capstone (OpenAI)",
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
