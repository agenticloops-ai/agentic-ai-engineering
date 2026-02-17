"""
Structured Output & Prompt Scaffolding (OpenAI)

Demonstrates techniques for getting parseable structured output from OpenAI:
1. JSON via prompt instructions — asking for JSON in the system prompt
2. Markdown scaffolding — using structured sections to guide output
3. JSON schema enforcement — OpenAI's native structured output feature

All three methods extract the same product information from one description,
making it easy to compare reliability across techniques.
"""

import json

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from common import OpenAITokenTracker, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# Schema that the LLM should populate (human-readable)
PRODUCT_SCHEMA = {
    "name": "string — product name",
    "category": "string — product category (e.g., Electronics, Clothing)",
    "price": "number — price in USD",
    "features": "list of strings — key product features",
    "in_stock": "boolean — whether the product is currently available",
}

# JSON schema for OpenAI's native structured output enforcement
PRODUCT_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "product_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Product name"},
            "category": {
                "type": "string",
                "description": "Product category (e.g., Electronics, Clothing)",
            },
            "price": {"type": "number", "description": "Price in USD"},
            "features": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key product features",
            },
            "in_stock": {
                "type": "boolean",
                "description": "Whether the product is currently available",
            },
        },
        "required": ["name", "category", "price", "features", "in_stock"],
        "additionalProperties": False,
    },
}

# Single product description — all three methods extract from this same input
PRODUCT_DESCRIPTION = (
    "The UltraSound Pro X1 wireless noise-cancelling headphones deliver studio-quality "
    "audio with 40mm custom drivers and adaptive ANC. Features include 30-hour battery "
    "life, multipoint Bluetooth 5.3 for connecting two devices simultaneously, and a "
    "foldable design with a premium carrying case. Available now at $249.99. "
    "Currently in stock and shipping within 24 hours."
)


class StructuredOutputClient:
    """Demonstrates structured output techniques with OpenAI's API."""

    def __init__(self, model: str, token_tracker: OpenAITokenTracker):
        self.client = OpenAI()
        self.model = model
        self.token_tracker = token_tracker

    def _call(self, instructions: str, user_input: str, **kwargs) -> str:
        """Make an API call and track tokens."""
        response = self.client.responses.create(
            model=self.model,
            temperature=0.0,
            max_output_tokens=512,
            instructions=instructions,
            input=user_input,
            **kwargs,
        )
        if hasattr(response, "usage") and response.usage:
            self.token_tracker.track(response.usage)
        return response.output_text or ""

    def extract_json_prompted(self, description: str) -> str:
        """Extract structured data by asking for JSON in the prompt."""
        schema_str = json.dumps(PRODUCT_SCHEMA, indent=2)
        instructions = (
            "You are a product data extraction assistant. Extract structured information "
            "from product descriptions.\n\n"
            f"Output ONLY valid JSON matching this schema:\n{schema_str}\n\n"
            "No markdown, no explanation — just the JSON object."
        )
        return self._call(instructions, description)

    def extract_with_scaffolding(self, description: str) -> str:
        """Use markdown sections to scaffold the input and guide the output."""
        schema_str = json.dumps(PRODUCT_SCHEMA, indent=2)
        # OpenAI works well with markdown-structured prompts
        instructions = (
            "You are a product data extraction assistant. You receive structured inputs "
            "and extract product data as JSON.\n\n"
            "Output ONLY valid JSON matching the provided schema. "
            "No markdown fences, no explanation."
        )
        user_input = (
            f"## Schema\n```json\n{schema_str}\n```\n\n"
            f"## Product Description\n{description}\n\n"
            "## Output\nExtract the product information as JSON:"
        )
        return self._call(instructions, user_input)

    def extract_with_schema(self, description: str) -> str:
        """Use OpenAI's native JSON schema enforcement — guaranteed valid JSON."""
        instructions = (
            "You are a product data extraction assistant. Extract structured information "
            "from product descriptions. Populate all fields based on the description."
        )
        # OpenAI's text format parameter enforces the schema at the API level
        return self._call(
            instructions,
            description,
            text={"format": PRODUCT_JSON_SCHEMA},
        )


def _try_parse_json(raw: str) -> dict | None:
    """Attempt to parse JSON, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("JSON parse failed: %s", e)
        return None


def _display_result(console: Console, method_name: str, raw: str) -> None:
    """Parse and display the JSON result from a structured output method."""
    parsed = _try_parse_json(raw)
    if parsed:
        formatted = json.dumps(parsed, indent=2)
        syntax = Syntax(formatted, "json", theme="monokai")
        console.print(Panel(syntax, title=f"{method_name} [green]VALID JSON[/green]"))
    else:
        console.print(Panel(raw[:300], title=f"{method_name} [red]PARSE FAILED[/red]"))


def main() -> None:
    """Run one product description through three structured output methods."""
    console = Console()
    token_tracker = OpenAITokenTracker()
    client = StructuredOutputClient("gpt-4.1", token_tracker)

    console.print(
        Panel(
            "[bold cyan]Structured Output & Prompt Scaffolding[/bold cyan]\n\n"
            "Comparing 3 techniques for extracting structured JSON from free-form text:\n"
            "  1. JSON via prompt instructions\n"
            "  2. Markdown scaffolding\n"
            "  3. JSON schema enforcement (OpenAI-specific)\n\n"
            "All three extract from the same product description for easy comparison.",
            title="Prompt Engineering — OpenAI",
        )
    )

    console.print(
        "\n[bold yellow]━━━ Product Description (input for all methods) ━━━[/bold yellow]"
    )
    console.print(Panel(PRODUCT_DESCRIPTION, border_style="dim"))

    schema_str = json.dumps(PRODUCT_SCHEMA, indent=2)

    # --- Method 1: Prompted JSON ---
    console.input("\n[dim]Press Enter to continue...[/dim]")
    console.print("\n[bold yellow]━━━ 1: Prompted JSON ━━━[/bold yellow]")
    console.print("[dim]Embed the schema in the instructions and ask for JSON output.[/dim]\n")
    prompt_1 = (
        "**Instructions:**\n"
        "```\n"
        "You are a product data extraction assistant...\n"
        f"Output ONLY valid JSON matching this schema:\n{schema_str}\n"
        "No markdown, no explanation — just the JSON object.\n"
        "```\n\n"
        "**Input:** _(raw product description)_\n"
    )
    console.print(Markdown(prompt_1))

    console.input("\n[dim]Press Enter to run...[/dim]")
    try:
        raw = client.extract_json_prompted(PRODUCT_DESCRIPTION)
        _display_result(console, "Prompted JSON", raw)
    except Exception as e:
        logger.error("Error in method 1: %s", e)

    # --- Method 2: Markdown Scaffolding ---
    console.input("\n[dim]Press Enter to continue...[/dim]")
    console.print("\n[bold yellow]━━━ 2: Markdown Scaffolding ━━━[/bold yellow]")
    console.print("[dim]Structure the input with markdown sections to guide the output.[/dim]\n")
    prompt_2 = (
        "**Instructions:**\n"
        "```\n"
        "You are a product data extraction assistant.\n"
        "Output ONLY valid JSON matching the provided schema.\n"
        "No markdown fences, no explanation.\n"
        "```\n\n"
        "**Input (markdown-structured):**\n"
        "```markdown\n"
        f"## Schema\n```json\n{schema_str}\n```\n\n"
        "## Product Description\n(product description here)\n\n"
        "## Output\nExtract the product information as JSON:\n"
        "```\n"
    )
    console.print(Markdown(prompt_2))

    console.input("\n[dim]Press Enter to run...[/dim]")
    try:
        raw = client.extract_with_scaffolding(PRODUCT_DESCRIPTION)
        _display_result(console, "Markdown Scaffolding", raw)
    except Exception as e:
        logger.error("Error in method 2: %s", e)

    # --- Method 3: Schema Enforcement ---
    console.input("\n[dim]Press Enter to continue...[/dim]")
    console.print("\n[bold yellow]━━━ 3: Schema Enforcement ━━━[/bold yellow]")
    console.print("[dim]API-level enforcement via text.format — guaranteed valid JSON.[/dim]\n")
    schema_preview = json.dumps(PRODUCT_JSON_SCHEMA, indent=2)
    prompt_3 = (
        "**Instructions:**\n"
        "```\n"
        "You are a product data extraction assistant...\n"
        "Populate all fields based on the description.\n"
        "```\n\n"
        "**Input:** _(raw product description)_\n\n"
        "**text.format (JSON schema):**\n"
        f"```json\n{schema_preview}\n```\n\n"
        "_The API guarantees the response conforms to this schema — no parsing needed._\n"
    )
    console.print(Markdown(prompt_3))

    console.input("\n[dim]Press Enter to run...[/dim]")
    try:
        raw = client.extract_with_schema(PRODUCT_DESCRIPTION)
        _display_result(console, "Schema Enforcement", raw)
    except Exception as e:
        logger.error("Error in method 3: %s", e)

    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
