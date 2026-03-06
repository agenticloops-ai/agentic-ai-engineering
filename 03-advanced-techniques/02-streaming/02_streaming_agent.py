"""
Streaming Agent with Tool Calls (Anthropic)

Demonstrates the hard part of streaming: handling tool_use blocks mid-stream.
The agent streams text in real-time, detects when Claude wants to call a tool,
executes it, feeds the result back, and resumes streaming — all while maintaining
a smooth, responsive terminal UI.
"""

import ast
import json
import operator
import random
from typing import Any

import anthropic
from anthropic.types import ContentBlock, TextBlock, ToolUseBlock
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from common import AnthropicTokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Use tools when they can provide accurate answers — don't guess at weather or math. "
    "After getting tool results, incorporate them naturally into your response. "
    "Keep responses concise and use markdown formatting."
)

# --- Tool definitions ---

TOOLS = [
    {
        "name": "get_weather",
        "description": (
            "Get current weather conditions for a city. "
            "Returns temperature, conditions, and humidity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (e.g., 'San Francisco', 'Tokyo', 'London')",
                },
            },
            "required": ["city"],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Evaluate a mathematical expression safely. Supports arithmetic operators "
            "(+, -, *, /, **, %), parentheses, and common functions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression to evaluate (e.g., '(15 * 3) + 42')",
                },
            },
            "required": ["expression"],
        },
    },
]


# --- Tool implementations ---

# Simulated weather data — no API key needed, keeps tutorial self-contained
WEATHER_DATA: dict[str, dict[str, Any]] = {
    "san francisco": {"temp_f": 62, "conditions": "Foggy", "humidity": 78},
    "new york": {"temp_f": 45, "conditions": "Partly cloudy", "humidity": 55},
    "tokyo": {"temp_f": 58, "conditions": "Clear", "humidity": 42},
    "london": {"temp_f": 48, "conditions": "Overcast", "humidity": 82},
    "paris": {"temp_f": 52, "conditions": "Light rain", "humidity": 75},
    "sydney": {"temp_f": 77, "conditions": "Sunny", "humidity": 60},
}


def get_weather(city: str) -> dict[str, Any]:
    """Simulated weather lookup with realistic data."""
    key = city.lower().strip()
    if key in WEATHER_DATA:
        data = WEATHER_DATA[key]
    else:
        # Generate plausible weather for unknown cities
        data = {
            "temp_f": random.randint(35, 85),
            "conditions": random.choice(["Clear", "Cloudy", "Partly cloudy", "Light rain"]),
            "humidity": random.randint(30, 90),
        }

    logger.info("Weather lookup: %s → %s", city, data["conditions"])
    return {"city": city, **data}


# Safe operators for math evaluation
SAFE_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate an AST node using only safe operators."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    elif isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        result: float = SAFE_OPERATORS[type(node.op)](left, right)
        return result
    elif isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
        result_u: float = SAFE_OPERATORS[type(node.op)](_safe_eval(node.operand))
        return result_u
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def calculate(expression: str) -> dict[str, Any]:
    """Safe math evaluator — no eval(), only arithmetic via AST parsing."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree)
        logger.info("Calculate: %s = %s", expression, result)
        return {"expression": expression, "result": result}
    except (ValueError, TypeError, ZeroDivisionError, SyntaxError) as e:
        logger.error("Calculation error: %s — %s", expression, e)
        return {"expression": expression, "error": str(e)}


TOOL_FUNCTIONS: dict[str, Any] = {
    "get_weather": get_weather,
    "calculate": calculate,
}


def execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool and return the JSON result string."""
    if name not in TOOL_FUNCTIONS:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = TOOL_FUNCTIONS[name](**tool_input)
        return json.dumps(result)
    except Exception as e:
        logger.error("Tool execution error (%s): %s", name, e)
        return json.dumps({"error": str(e)})


# --- Streaming agent ---


class StreamingAgent:
    """Agent that streams responses and handles tool calls mid-stream.

    The key challenge: a single API response can contain BOTH text blocks
    and tool_use blocks, interleaved. This agent streams text to the terminal
    in real-time, detects tool_use blocks as they arrive, executes tools,
    and loops back for the model's follow-up response.
    """

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker) -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker
        self.messages: list[dict[str, Any]] = []

    def run(self, user_input: str, console: Console) -> str:
        """Run the full agent loop: stream → detect tools → execute → resume.

        This loop continues until the model returns stop_reason="end_turn",
        meaning it has no more tool calls to make.
        """
        self.messages.append({"role": "user", "content": user_input})
        full_response_text = ""
        iteration = 0
        max_iterations = 10  # Safety limit to prevent infinite loops

        while iteration < max_iterations:
            iteration += 1
            logger.info("Agent loop iteration %d", iteration)

            # Stream the response, rendering text and detecting tool calls
            response_message = self._stream_response(console)

            # Add the assistant's full response to conversation history
            self.messages.append({"role": "assistant", "content": response_message.content})

            # Collect any text from this response
            for block in response_message.content:
                if isinstance(block, TextBlock) and block.text:
                    full_response_text += block.text

            # If no tool calls, we're done
            if response_message.stop_reason != "tool_use":
                logger.info("Agent complete (stop_reason: %s)", response_message.stop_reason)
                break

            # Execute tool calls and feed results back
            tool_results = self._execute_tool_calls(response_message.content, console)
            self.messages.append({"role": "user", "content": tool_results})

            # Next iteration will stream the model's follow-up

        return full_response_text

    def _stream_response(self, console: Console) -> anthropic.types.Message:
        """Stream a single API call, rendering text and tool calls in real-time.

        Returns the complete accumulated message for history tracking.
        """
        with self.client.messages.stream(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=self.messages,
            tools=TOOLS,
        ) as stream:
            self._render_stream(stream, console)
            final_message = stream.get_final_message()
            self.token_tracker.track(final_message.usage)
            return final_message

    def _render_stream(self, stream: anthropic.MessageStream, console: Console) -> None:
        """Render a mixed stream of text and tool_use blocks.

        This is the core method that makes streaming with tools work:
        - Text deltas → rendered live as markdown
        - tool_use blocks → displayed as status indicators
        - input_json_delta → tool parameters accumulating (logged, not displayed)
        """
        accumulated_text = ""
        current_block_type: str | None = None
        current_tool_name: str | None = None
        live: Live | None = None

        try:
            for event in stream:
                if event.type == "content_block_start":
                    current_block_type = event.content_block.type

                    if current_block_type == "text":
                        # Start live rendering for text
                        live = Live(Markdown(""), refresh_per_second=15, console=console)
                        live.start()

                    elif current_block_type == "tool_use":
                        # Tool call starting — show what's being called
                        current_tool_name = event.content_block.name
                        console.print(
                            f"\n[dim]  ⚡ Calling [bold]{current_tool_name}[/bold]...[/dim]",
                            end="",
                        )

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        # Text arriving — update the live display
                        accumulated_text += event.delta.text
                        if live is not None:
                            live.update(Markdown(accumulated_text))

                    elif event.delta.type == "input_json_delta":
                        # Tool input parameters streaming in
                        # We don't display these — just let them accumulate
                        # The SDK's get_final_message() gives us the parsed input
                        logger.debug("Tool input delta: %s", event.delta.partial_json)

                elif event.type == "content_block_stop":
                    if current_block_type == "text" and live is not None:
                        # Text block finished — stop live rendering
                        live.stop()
                        live = None

                    elif current_block_type == "tool_use":
                        # Tool call block finished
                        console.print()  # newline after the "Calling..." message

                    current_block_type = None
                    current_tool_name = None

        finally:
            # Ensure live display is stopped if an error occurs mid-stream
            if live is not None:
                live.stop()

    def _execute_tool_calls(
        self, content: list[ContentBlock], console: Console
    ) -> list[dict[str, Any]]:
        """Execute all tool calls from a response and format results for the API."""
        tool_results = []

        for block in content:
            if isinstance(block, ToolUseBlock):
                logger.info("Executing tool: %s(%s)", block.name, json.dumps(block.input))
                console.print(
                    f"[dim]  → {block.name}({json.dumps(block.input, separators=(',', ':'))})[/dim]"
                )

                result = execute_tool(block.name, block.input)
                console.print(
                    f"[dim]  ✓ Result: {result[:100]}{'...' if len(result) > 100 else ''}[/dim]"
                )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

        return tool_results

    def reset(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        logger.info("Conversation history cleared")


def main() -> None:
    """Interactive streaming agent with tool use."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    agent = StreamingAgent(MODEL, token_tracker)

    console.print(
        Panel(
            "[bold cyan]Streaming Agent with Tools[/bold cyan]\n\n"
            "Watch responses stream in real-time — even when Claude calls tools mid-response.\n\n"
            "[bold]Available tools:[/bold]\n"
            "  🌤️  [green]get_weather[/green] — current weather for any city\n"
            "  🔢 [green]calculate[/green]    — evaluate math expressions\n\n"
            "[bold]Try these prompts:[/bold]\n"
            '  • "What\'s the weather like in San Francisco?"\n'
            '  • "Calculate the compound interest: 10000 * (1 + 0.05) ** 10"\n'
            '  • "Compare the weather in Tokyo and London, and calculate the '
            'temperature difference"\n\n'
            "Type [bold]clear[/bold] to reset, [bold]quit[/bold] to exit.",
            title="02-streaming / 02 — Streaming Agent",
        )
    )

    while True:
        console.print("\n[bold green]You:[/bold green] ", end="")
        try:
            user_input = input().strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Interrupted.[/yellow]")
            break

        if not user_input or user_input.lower() in ("quit", "exit"):
            console.print("[yellow]Ending session...[/yellow]")
            break

        if user_input.lower() == "clear":
            agent.reset()
            console.print("[dim]Conversation cleared.[/dim]")
            continue

        try:
            console.print("\n[bold blue]Claude:[/bold blue]")
            agent.run(user_input, console)
        except anthropic.APIError as e:
            logger.error("API error: %s", e)
            console.print(f"\n[red]API error: {e}[/red]")

    console.print()
    token_tracker.report()
    console.print(f"[dim]Messages exchanged: {len(agent.messages)}[/dim]")


if __name__ == "__main__":
    main()
