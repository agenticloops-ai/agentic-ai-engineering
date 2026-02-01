"""
Augmented LLM — Codebase Navigator (Anthropic)

Demonstrates the "Augmented LLM" pattern: an LLM enhanced with retrieval (RAG),
tools, and memory. This is the foundational building block of all agentic systems,
as described in Anthropic's "Building Effective Agents" guide.

The Codebase Navigator helps engineers explore and understand unfamiliar codebases.
Point it at any GitHub repo, and it will clone, index, and answer questions using
semantic search — while maintaining memory across sessions.
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

# Load environment variables
load_dotenv(find_dotenv())

logger = setup_logging(__name__)


SYSTEM_PROMPT = """You are a Codebase Navigator — an AI assistant that helps software engineers \
explore and understand codebases.

## Your Capabilities

You have access to tools for:
- Cloning and indexing GitHub repositories (clone_and_index)
- Listing indexed repositories (list_repos)
- Searching code semantically (search_code)
- Reading full file contents (read_file)
- Exploring directory structures (list_directory)
- Finding exact patterns with regex (grep)
- Saving memories for future sessions (save_memory)
- Recalling saved memories (recall_memory)

## How to Help Users

When a user mentions a GitHub repo (like "pallets/flask" or "look at the httpie repo"):
1. Use clone_and_index to clone and index it first
2. Then answer their questions using search_code, read_file, etc.

Use search_code for semantic/conceptual questions:
- "how does authentication work?"
- "where is the database connection handled?"

Use grep for exact matches:
- "find all TODO comments"
- "where is UserModel defined?"

Use read_file when you need full context after finding relevant chunks.

## Memory

Save important insights to memory, especially:
- Architectural patterns you discover
- Key files and their purposes
- Connections between different repos
- User preferences for how they like information presented

Check recall_memory at the start of conversations to remember context.

## Response Style

- Be concise but thorough
- Show relevant code snippets with file paths and line numbers
- Explain architectural decisions when you discover them
- Suggest related areas to explore"""


# -- Tool registry ----------------------------------------------------------


def _build_tool_definitions() -> list[dict[str, Any]]:
    """Collect all tool definitions from tool modules."""
    from tools.files import FILE_TOOLS
    from tools.memory import MEMORY_TOOLS
    from tools.repo import REPO_TOOLS
    from tools.search import SEARCH_TOOLS

    return MEMORY_TOOLS + REPO_TOOLS + FILE_TOOLS + SEARCH_TOOLS


class CodeNavigatorAgent:
    """
    An LLM augmented with retrieval, tools, and memory.

    Implements the agentic loop: send message → execute tools → send results → repeat
    until the LLM responds with just text.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = AnthropicTokenTracker()
        self.tools = _build_tool_definitions()
        self.messages: list[dict[str, Any]] = []
        self.max_iterations = 15

        # Initialize shared components (the three augmentations)
        from indexer.embedder import Embedder
        from store.memory import MemoryStore
        from store.vector import VectorStore

        self.memory = MemoryStore()
        self.vector_store = VectorStore()
        self.embedder = Embedder()

    def _build_system_prompt(self) -> str:
        """Build system prompt with memory context."""
        memory_summary = self.memory.summary()
        if memory_summary and memory_summary != "No memories stored yet.":
            return SYSTEM_PROMPT + f"\n\n## Recalled Memories\n{memory_summary}"
        return SYSTEM_PROMPT

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        """Dispatch a tool call to the appropriate handler."""
        from tools.files import execute_list_directory, execute_read_file
        from tools.memory import execute_recall_memory, execute_save_memory
        from tools.repo import execute_clone_and_index, execute_list_repos
        from tools.search import execute_grep, execute_search_code

        dispatch: dict[str, Any] = {
            "save_memory": lambda inp: execute_save_memory(self.memory, inp),
            "recall_memory": lambda inp: execute_recall_memory(self.memory, inp),
            "clone_and_index": lambda inp: execute_clone_and_index(
                self.vector_store, self.embedder, inp
            ),
            "list_repos": lambda inp: execute_list_repos(self.vector_store, inp),
            "read_file": lambda inp: execute_read_file(self.vector_store, inp),
            "list_directory": lambda inp: execute_list_directory(self.vector_store, inp),
            "search_code": lambda inp: execute_search_code(self.vector_store, self.embedder, inp),
            "grep": lambda inp: execute_grep(self.vector_store, self.embedder, inp),
        }

        handler = dispatch.get(name)
        if not handler:
            return f"Unknown tool: {name}"

        try:
            return str(handler(tool_input))
        except Exception as e:
            logger.error("Tool '%s' failed: %s", name, e)
            return f"Error executing {name}: {e}"

    def chat(self, user_message: str, console: Console) -> str:
        """Send a message and handle the agentic tool-use loop."""
        self.messages.append({"role": "user", "content": user_message})

        for _iteration in range(self.max_iterations):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=self._build_system_prompt(),
                    tools=self.tools,
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
            assistant_content = []
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

            # Ensure assistant content is never empty (API requirement)
            if not assistant_content:
                assistant_content = [{"type": "text", "text": "Done."}]
                text_parts = ["Done."]

            self.messages.append({"role": "assistant", "content": assistant_content})

            # If no tool use, return the text response
            if response.stop_reason == "end_turn":
                return "\n".join(text_parts) if text_parts else "Done."

            # Execute each tool and print progress
            tool_results = []
            for tool_use in tool_uses:
                # Print tool invocation for educational transparency
                input_summary = json.dumps(tool_use.input, separators=(",", ":"))
                if len(input_summary) > 80:
                    input_summary = input_summary[:77] + "..."
                console.print(f"  [dim][tool: {tool_use.name}] {input_summary}[/dim]")

                result = self._execute_tool(tool_use.name, tool_use.input)

                # Print brief result
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

        return "Reached maximum iterations. Please try a more specific question."


# -- Main -------------------------------------------------------------------


def main() -> None:
    """Main orchestration function."""

    agent = CodeNavigatorAgent()

    console = Console()

    console.print(
        Panel(
            "An LLM enhanced with [green]Retrieval (RAG)[/green], "
            "[yellow]Tools[/yellow], and [magenta]Memory[/magenta].\n\n"
            "Try:\n"
            "  • index the flask repo from pallets/flask\n"
            "  • how does routing work?\n"
            "  • find all TODO comments\n"
            "  • list the directory structure\n\n"
            "[dim]Repos use GitHub format: owner/repo (e.g., pallets/flask)[/dim]\n"
            "Type 'quit' to exit.",
            title="[bold cyan]Codebase Navigator[/bold cyan]",
        )
    )

    try:
        while True:
            console.print("\n[bold green]You:[/bold green] ", end="")
            try:
                user_input = input().strip()
            except EOFError:
                break

            if user_input.lower() in ("exit", "quit", "q", ""):
                console.print("\n[yellow]Ending session...[/yellow]")
                break

            response = agent.chat(user_input, console)

            if response:
                console.print("\n[bold blue]Navigator:[/bold blue]")
                console.print(Markdown(response))

            agent.token_tracker.report()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
