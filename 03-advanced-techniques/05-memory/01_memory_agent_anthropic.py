"""Memory Systems — Personal assistant with three-tier memory persistence.

Demonstrates working memory (session buffer), episodic memory (JSON-persisted events),
and semantic memory (ChromaDB vector store) in an agentic chat loop. The agent uses
tools to remember, recall, and forget information across sessions.
"""

import json
import time
from typing import Any

import anthropic
from anthropic.types import TextBlock, ToolUseBlock
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common import AnthropicTokenTracker, setup_logging
from memory import MemoryManager

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = """\
You are a personal assistant with persistent memory. You remember information about the user \
across sessions using a three-tier memory system:

1. **Working memory** — temporary session notes (auto-cleared)
2. **Episodic memory** — timestamped events and interactions (persisted to JSON)
3. **Semantic memory** — facts, preferences, and knowledge (persisted to vector database)

## Memory Guidelines

- When the user shares personal information (name, preferences, facts), store it in \
**semantic** memory with appropriate importance
- When notable events or interactions happen, store them in **episodic** memory
- Use **recall** proactively to check if you already know something before asking
- Adjust importance scores: routine info = 0.3-0.5, personal details = 0.6-0.8, \
critical info = 0.9-1.0
- Be transparent about what you remember — tell the user when you recall something

{memory_context}"""

# Three tools the agent uses to manage memory
MEMORY_TOOLS = [
    {
        "name": "remember",
        "description": (
            "Store information in memory. Use 'semantic' for facts, preferences, and knowledge. "
            "Use 'episodic' for events and interactions. Use 'working' for temporary session notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["working", "episodic", "semantic"],
                    "description": "Which memory tier to store in",
                },
                "importance": {
                    "type": "number",
                    "description": "Importance score from 0.0 to 1.0",
                    "default": 0.5,
                },
            },
            "required": ["content", "memory_type"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Search across all memory tiers for relevant information. "
            "Use this to check what you know before asking the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memory",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "forget",
        "description": "Remove a specific memory by its ID and type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "The ID of the memory to delete",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["episodic", "semantic"],
                    "description": "Which memory tier to delete from",
                },
            },
            "required": ["memory_id", "memory_type"],
        },
    },
]


class MemoryAgent:
    """Personal assistant with three-tier memory and tool-use loop."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic()
        self.token_tracker = AnthropicTokenTracker()
        self.memory = MemoryManager()
        self.messages: list[dict[str, Any]] = []
        self.max_iterations = 10

    def _build_system_prompt(self) -> str:
        """Inject recalled memories into the system prompt."""
        memory_context = self.memory.build_memory_context()
        return SYSTEM_PROMPT.format(memory_context=memory_context)

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        """Dispatch a tool call to the appropriate MemoryManager method."""
        try:
            if name == "remember":
                return self.memory.remember(
                    content=tool_input["content"],
                    memory_type=tool_input["memory_type"],
                    importance=tool_input.get("importance", 0.5),
                )
            elif name == "recall":
                return self.memory.recall(
                    query=tool_input["query"],
                    limit=tool_input.get("limit", 5),
                )
            elif name == "forget":
                return self.memory.forget(
                    memory_id=tool_input["memory_id"],
                    memory_type=tool_input["memory_type"],
                )
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            logger.error("Tool '%s' failed: %s", name, e)
            return f"Error executing {name}: {e}"

    def chat(self, user_message: str, console: Console) -> str:
        """Send a message and handle the agentic tool-use loop."""
        self.messages.append({"role": "user", "content": user_message})

        for _iteration in range(self.max_iterations):
            try:
                response = self.client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    system=self._build_system_prompt(),
                    tools=MEMORY_TOOLS,
                    messages=self.messages,
                )
            except anthropic.RateLimitError:
                logger.warning("Rate limited — waiting 30s before retry...")
                time.sleep(30)
                continue
            except anthropic.APIError as e:
                logger.error("API error: %s", e)
                return f"API error: {e}"

            self.token_tracker.track(response.usage)

            # Collect response content
            assistant_content: list[dict[str, Any]] = []
            text_parts: list[str] = []
            tool_uses: list[ToolUseBlock] = []

            for block in response.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                    assistant_content.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    tool_uses.append(block)
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )

            if not assistant_content:
                assistant_content = [{"type": "text", "text": "Done."}]
                text_parts = ["Done."]

            self.messages.append({"role": "assistant", "content": assistant_content})

            # If no tool use, return the text response
            if response.stop_reason == "end_turn":
                return "\n".join(text_parts) if text_parts else "Done."

            # Execute each tool and show progress
            tool_results: list[dict[str, Any]] = []
            for tool_use in tool_uses:
                input_summary = json.dumps(tool_use.input, separators=(",", ":"))
                if len(input_summary) > 80:
                    input_summary = input_summary[:77] + "..."
                console.print(f"  [dim][tool: {tool_use.name}] {input_summary}[/dim]")

                result = self._execute_tool(tool_use.name, tool_use.input)

                result_preview = result.split("\n")[0][:80]
                console.print(f"  [dim]  → {result_preview}[/dim]")

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    }
                )

            self.messages.append({"role": "user", "content": tool_results})

        return "Reached maximum iterations."

    def loaded_memory_count(self) -> int:
        """Count of persisted memories loaded from previous sessions."""
        stats = self.memory.get_stats()
        total: int = stats["episodic"]["count"] + stats["semantic"]["count"]
        return total


def main() -> None:
    """Run the memory-augmented personal assistant."""
    console = Console()

    agent = MemoryAgent()
    loaded = agent.loaded_memory_count()

    # Welcome panel
    status_line = (
        f"[green]Loaded {loaded} memories from previous sessions[/green]"
        if loaded
        else ("[dim]No previous memories — this is a fresh start[/dim]")
    )

    header = Panel(
        "[bold cyan]Memory Systems — Personal Assistant[/bold cyan]\n\n"
        "A personal assistant that remembers across sessions using three memory tiers:\n"
        "  [bold]Working[/bold]  — temporary session buffer (auto-cleared)\n"
        "  [bold]Episodic[/bold] — timestamped events (persisted to JSON)\n"
        "  [bold]Semantic[/bold] — facts and knowledge (persisted to ChromaDB)\n\n"
        f"{status_line}\n\n"
        "[bold]Try these:[/bold]\n"
        '  • "Hi, I\'m Alex and I work at Acme Corp"\n'
        '  • "I prefer Python over JavaScript"\n'
        '  • "What do you remember about me?" (after restart)\n\n'
        '[dim]Type "exit" or "quit" to end the session[/dim]',
        title="Tutorial 05 — Memory Systems",
    )
    console.print(header)

    try:
        while True:
            console.print("\n[bold green]You:[/bold green] ", end="")
            try:
                user_input = input().strip()
            except EOFError:
                break

            if user_input.lower() in ("exit", "quit", "q", ""):
                break

            response = agent.chat(user_input, console)
            if response:
                console.print("\n[bold blue]Assistant:[/bold blue]")
                console.print(Markdown(response))

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    # Consolidate session into long-term memory
    console.print("\n[dim]Consolidating session memories...[/dim]")
    saved = agent.memory.consolidate(agent.messages, agent.client, MODEL)
    if saved:
        console.print(f"[green]Saved {len(saved)} memories for next session:[/green]")
        for item in saved:
            console.print(f"  [dim]{item}[/dim]")
    else:
        console.print("[dim]No new memories to consolidate.[/dim]")

    console.print()
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
