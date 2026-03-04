"""
Tool Output Context Engineering (Anthropic)

Demonstrates three strategies for managing tool output in agent context windows:
naive (raw injection), truncation (character cap), and summarization (LLM extraction).
Uses simulated business tools that return realistically large JSON payloads to show
how tool outputs dominate context consumption.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, interactive_menu, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

# Model configuration
MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = (
    "You are a business data assistant with access to CRM, order, and product tools. "
    "Answer user questions by calling the appropriate tools. Be concise and reference "
    "specific data points from tool results."
)

# Artificially low budget so compression triggers quickly in the demo
MAX_CONTEXT_TOKENS = 4096
RESPONSE_RESERVE = 2048
RECENT_MESSAGES_TO_KEEP = 4

# Strategy constants
TRUNCATE_MAX_CHARS = 500

STRATEGIES = {
    "naive": "Raw tool output injected directly (baseline — fills context fast)",
    "truncate": f"Cap tool output at {TRUNCATE_MAX_CHARS} chars (free, lossy)",
    "summarize": "LLM extracts key facts from tool output (extra API call, preserves meaning)",
}

# --- Simulated Business Tools ---

TOOLS = [
    {
        "name": "lookup_customer",
        "description": (
            "Look up a customer by name. Returns contact info, address, account history, "
            "preferences, and recent support tickets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Customer name to search for",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_order_history",
        "description": (
            "Get order history for a customer. Returns a list of orders with line items, "
            "totals, dates, and fulfillment statuses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer ID (e.g. CUST-1001)",
                },
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "search_products",
        "description": (
            "Search the product catalog by keyword. Returns matching products with "
            "descriptions, specifications, pricing, and availability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword or phrase",
                },
            },
            "required": ["query"],
        },
    },
]


DB_PATH = Path(__file__).parent / "database.json"


class MockDatabaseService:
    """Simulated business database loaded from JSON."""

    def __init__(self, db_path: Path) -> None:
        self.data: dict[str, Any] = json.loads(db_path.read_text())
        logger.info("Loaded mock database from %s", db_path.name)

    def get_customer(self, name: str) -> dict:
        """Look up a customer by name, returning the first match."""
        name_lower = name.lower()
        for customer in self.data["customers"].values():
            if name_lower in customer["name"].lower():
                return customer
        return {"error": f"Customer '{name}' not found"}

    def get_orders(self, customer_id: str) -> dict:
        """Get order history for a customer ID."""
        if customer_id in self.data["orders"]:
            return self.data["orders"][customer_id]
        return {"error": f"No orders found for customer '{customer_id}'"}

    def search_products(self, query: str) -> dict:
        """Search the product catalog by keyword."""
        query_lower = query.lower()
        matches = [p for p in self.data["products"] if query_lower in json.dumps(p).lower()]
        # Return all products if no specific matches (simulates broad search)
        results = matches if matches else self.data["products"]
        return {"query": query, "total_results": len(results), "products": results}


# --- Dataclasses (self-contained, same pattern as script 01) ---


@dataclass
class ContextBudget:
    """Token budget allocation across context components."""

    max_context: int
    system_tokens: int = 0
    response_reserve: int = RESPONSE_RESERVE

    @property
    def history_budget(self) -> int:
        """Available tokens for conversation history."""
        return self.max_context - self.system_tokens - self.response_reserve


@dataclass
class TokenSnapshot:
    """Snapshot of token usage for budget display."""

    system: int = 0
    history: int = 0
    history_budget: int = 0
    reserve: int = 0
    message_count: int = 0
    compression_count: int = 0


# --- Core Agent ---


class ToolContextAgent:
    """Agent demonstrating tool output context management strategies."""

    def __init__(
        self,
        model: str,
        strategy: str,
        max_context: int,
        token_tracker: AnthropicTokenTracker,
        db: MockDatabaseService,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.strategy = strategy
        self.token_tracker = token_tracker
        self.db = db
        self.messages: list[dict] = []
        self.budget = ContextBudget(max_context=max_context)
        self.compression_count = 0

        # Tool name → service method mapping
        self.tool_handlers: dict[str, Any] = {
            "lookup_customer": lambda **kw: self.db.get_customer(kw["name"]),
            "get_order_history": lambda **kw: self.db.get_orders(kw["customer_id"]),
            "search_products": lambda **kw: self.db.search_products(kw["query"]),
        }

        # Measure system prompt + tool definitions once at init
        self.budget.system_tokens = self._count_tokens([])
        logger.info(
            "Context budget — system+tools: %d, history: %d, reserve: %d, strategy: %s",
            self.budget.system_tokens,
            self.budget.history_budget,
            self.budget.response_reserve,
            self.strategy,
        )

    def chat(self, user_input: str) -> str:
        """Agent loop: send → detect tool calls → execute → process results → loop."""
        self.messages.append({"role": "user", "content": user_input})

        # Compress before sending if history exceeds budget
        self._compress_if_needed()

        while True:
            logger.info(
                "Sending request (messages: %d, history tokens: ~%d/%d)",
                len(self.messages),
                self._count_tokens(self.messages) - self.budget.system_tokens,
                self.budget.history_budget,
            )

            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.budget.response_reserve,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages,
            )

            self.token_tracker.track(response.usage)

            # Collect text and tool-use blocks
            tool_uses = []
            text_parts = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            # Add assistant response to history
            self.messages.append({"role": "assistant", "content": response.content})

            # If no tool use, return the text response
            if response.stop_reason != "tool_use" or not tool_uses:
                return "\n".join(text_parts) if text_parts else ""

            # Execute tools and apply strategy to results
            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_input = tool_use.input

                logger.info("Executing tool: %s(%s)", tool_name, json.dumps(tool_input))

                # Execute tool via database service
                raw_result = json.dumps(self.tool_handlers[tool_name](**tool_input), indent=2)

                # Apply context strategy to the tool output
                processed_result = self._process_tool_result(tool_name, raw_result)

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": processed_result,
                    }
                )

            # Add tool results and loop for next response
            self.messages.append({"role": "user", "content": tool_results})

            # Compress again if tool results pushed us over budget
            self._compress_if_needed()

    def _process_tool_result(self, tool_name: str, raw_result: str) -> str:
        """Apply selected strategy to tool output before injecting into context."""
        raw_chars = len(raw_result)

        if self.strategy == "naive":
            logger.info("[naive] Tool %s: %d chars injected as-is", tool_name, raw_chars)
            return raw_result

        if self.strategy == "truncate":
            processed = self._truncate_result(raw_result)
            logger.info("[truncate] Tool %s: %d → %d chars", tool_name, raw_chars, len(processed))
            return processed

        if self.strategy == "summarize":
            processed = self._summarize_result(tool_name, raw_result)
            logger.info("[summarize] Tool %s: %d → %d chars", tool_name, raw_chars, len(processed))
            return processed

        return raw_result

    def _truncate_result(self, result: str) -> str:
        """Cap at TRUNCATE_MAX_CHARS with truncation indicator."""
        if len(result) <= TRUNCATE_MAX_CHARS:
            return result
        return result[:TRUNCATE_MAX_CHARS] + "\n... [TRUNCATED — output exceeded limit]"

    def _summarize_result(self, tool_name: str, result: str) -> str:
        """LLM call to extract key facts from tool output."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=(
                "Extract the key facts from this tool output into a concise summary. "
                "Preserve all names, IDs, numbers, dates, and statuses. "
                "Use a flat bullet-point format. Be brief but complete."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Tool: {tool_name}\n\nOutput:\n{result}",
                }
            ],
        )

        self.token_tracker.track(response.usage)
        return str(response.content[0].text)

    def _count_tokens(self, messages: list[dict]) -> int:
        """Count tokens using the token counting API."""
        msgs = messages if messages else [{"role": "user", "content": "."}]
        result = self.client.messages.count_tokens(
            model=self.model,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=msgs,
        )
        return result.input_tokens

    def _compress_if_needed(self) -> None:
        """If history exceeds budget, summarize oldest messages."""
        history_tokens = self._count_tokens(self.messages) - self.budget.system_tokens

        if history_tokens <= self.budget.history_budget:
            return

        logger.info(
            "History (%d tokens) exceeds budget (%d tokens) — compressing",
            history_tokens,
            self.budget.history_budget,
        )

        # Split: keep recent messages verbatim, summarize the rest
        keep_count = min(RECENT_MESSAGES_TO_KEEP, len(self.messages))
        old_messages = self.messages[:-keep_count] if keep_count > 0 else self.messages
        recent_messages = self.messages[-keep_count:] if keep_count > 0 else []

        if not old_messages:
            logger.warning("No messages to compress — budget may be too small")
            return

        old_tokens = self._count_tokens(old_messages) - self.budget.system_tokens

        # Summarize old messages
        summary = self._summarize_messages(old_messages)

        # Replace old messages with summary
        summary_message = {
            "role": "user",
            "content": (
                f"[Previous conversation summary]\n{summary}\n"
                "[End of summary — continue the conversation from here]"
            ),
        }

        # Ensure alternating roles: summary (user) then recent messages
        if recent_messages and recent_messages[0]["role"] == "user":
            self.messages = [
                summary_message,
                {"role": "assistant", "content": "Understood, I have the conversation context."},
                *recent_messages,
            ]
        else:
            self.messages = [summary_message, *recent_messages]

        new_tokens = self._count_tokens(self.messages) - self.budget.system_tokens
        self.compression_count += 1

        logger.info(
            "Compressed %d messages: %d → %d tokens (saved %d tokens)",
            len(old_messages),
            old_tokens,
            new_tokens,
            old_tokens - new_tokens,
        )

    def _summarize_messages(self, messages: list[dict]) -> str:
        """Use LLM to summarize a block of messages including tool interactions."""
        parts = []
        for m in messages:
            role = "User" if m["role"] == "user" else "Assistant"
            content = m["content"]
            # Handle tool result messages (list of dicts)
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        texts.append(f"[Tool result: {item.get('content', '')[:200]}...]")
                    elif isinstance(item, dict) and hasattr(item, "text"):
                        texts.append(str(item))
                    else:
                        texts.append(str(item))
                content = "\n".join(texts)
            elif not isinstance(content, str):
                content = str(content)
            parts.append(f"{role}: {content}")

        transcript = "\n".join(parts)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=(
                "Summarize the following conversation concisely. "
                "Preserve key facts, data points, customer names, order IDs, and tool results. "
                "Write in third person past tense. Be brief but thorough."
            ),
            messages=[{"role": "user", "content": transcript}],
        )

        self.token_tracker.track(response.usage)
        return str(response.content[0].text)

    def get_token_snapshot(self) -> TokenSnapshot:
        """Budget state for visualization."""
        history_tokens = 0
        if self.messages:
            history_tokens = self._count_tokens(self.messages) - self.budget.system_tokens

        return TokenSnapshot(
            system=self.budget.system_tokens,
            history=history_tokens,
            history_budget=self.budget.history_budget,
            reserve=self.budget.response_reserve,
            message_count=len(self.messages),
            compression_count=self.compression_count,
        )


# --- UI ---


def _render_budget_display(console: Console, snapshot: TokenSnapshot) -> None:
    """Render the context budget visualization."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Component", style="dim")
    table.add_column("Tokens", justify="right")
    table.add_column("Bar", min_width=30)

    usage_ratio = snapshot.history / snapshot.history_budget if snapshot.history_budget > 0 else 0
    bar_width = 25
    filled = int(usage_ratio * bar_width)
    bar_color = "green" if usage_ratio < 0.7 else "yellow" if usage_ratio < 0.9 else "red"
    bar = f"[{bar_color}]{'█' * filled}[/{bar_color}][dim]{'░' * (bar_width - filled)}[/dim]"

    table.add_row("System+Tools", f"[cyan]{snapshot.system:,}[/cyan]", "[dim]fixed[/dim]")
    table.add_row(
        "History",
        f"[{bar_color}]{snapshot.history:,}[/{bar_color}] / {snapshot.history_budget:,}",
        bar,
    )
    table.add_row("Response Reserve", f"[cyan]{snapshot.reserve:,}[/cyan]", "[dim]max_tokens[/dim]")

    footer = f"Messages: {snapshot.message_count}"
    if snapshot.compression_count > 0:
        footer += f" │ Compressions: {snapshot.compression_count}"

    console.print(
        Panel(table, title="Context Budget", subtitle=footer, border_style="dim", padding=(0, 1))
    )


def main() -> None:
    """Main orchestration function for the tool context engineering demo."""
    console = Console()

    # Strategy selection
    strategy_items = [f"{name} — {desc}" for name, desc in STRATEGIES.items()]
    header = Panel(
        "[bold cyan]Tool Output Context Engineering[/bold cyan]\n\n"
        "Tool outputs are the biggest context consumers in agent systems.\n"
        "A single API call can return 1000+ tokens of JSON.\n\n"
        "Select a strategy to see how it affects context usage:",
        border_style="cyan",
    )

    selected = interactive_menu(
        console,
        items=strategy_items,
        title="Context Strategy",
        header=header,
    )

    if selected is None:
        console.print("[yellow]Exiting.[/yellow]")
        return

    # Extract strategy name from selection
    strategy = selected.split(" — ")[0]
    console.clear()

    token_tracker = AnthropicTokenTracker()
    db = MockDatabaseService(DB_PATH)
    agent = ToolContextAgent(MODEL, strategy, MAX_CONTEXT_TOKENS, token_tracker, db)

    # Strategy-specific welcome
    strategy_hints = {
        "naive": (
            "Raw tool outputs will be injected directly into context.\n"
            "Watch how 2-3 tool calls fill the entire budget!"
        ),
        "truncate": (
            f"Tool outputs will be capped at {TRUNCATE_MAX_CHARS} characters.\n"
            "This is free but may lose important data from the end of results."
        ),
        "summarize": (
            "An LLM will extract key facts from each tool output before injection.\n"
            "This costs an extra API call per tool use but preserves meaning."
        ),
    }

    console.print(
        Panel(
            f"[bold cyan]Strategy: {strategy.upper()}[/bold cyan]\n\n"
            f"{strategy_hints[strategy]}\n\n"
            f"Context budget: {MAX_CONTEXT_TOKENS:,} tokens total, "
            f"~{agent.budget.history_budget:,} for history.\n\n"
            "Try: 'Look up customer Alice Johnson' then 'Show her order history'\n"
            "Type [bold]'quit'[/bold] or [bold]'exit'[/bold] to end.",
            title="Business Data Agent",
        )
    )

    # Show initial budget
    _render_budget_display(console, agent.get_token_snapshot())

    while True:
        console.print("\n[bold green]You:[/bold green] ", end="")
        user_input = input().strip()

        if user_input.lower() in ["quit", "exit", ""]:
            console.print("\n[yellow]Ending session...[/yellow]")
            break

        try:
            response = agent.chat(user_input)

            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(response))

            # Show budget after each turn
            console.print()
            _render_budget_display(console, agent.get_token_snapshot())

        except Exception as e:
            logger.error("Error during chat: %s", e)
            console.print(f"\n[red]Error: {e}[/red]")
            break

    # Final report
    console.print()
    token_tracker.report()
    console.print(
        f"\n[dim]Messages: {len(agent.messages)} │ "
        f"Compressions: {agent.compression_count} │ "
        f"Strategy: {strategy}[/dim]"
    )


if __name__ == "__main__":
    main()
