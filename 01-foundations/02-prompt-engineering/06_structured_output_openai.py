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


def main() -> None:
    """Run one product description through three structured output methods."""
    console = Console()
    token_tracker = OpenAITokenTracker()
    client = StructuredOutputClient("gpt-4o", token_tracker)

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

    console.print("\n[bold yellow]━━━ Product Description ━━━[/bold yellow]")
    console.print(Panel(PRODUCT_DESCRIPTION, border_style="dim"))

    methods = {
        "Prompted JSON": client.extract_json_prompted,
        "Markdown Scaffolding": client.extract_with_scaffolding,
        "Schema Enforcement": client.extract_with_schema,
    }

    for method_name, method in methods.items():
        logger.info("Method: %s", method_name)
        try:
            raw = method(PRODUCT_DESCRIPTION)
            parsed = _try_parse_json(raw)

            if parsed:
                formatted = json.dumps(parsed, indent=2)
                syntax = Syntax(formatted, "json", theme="monokai")
                console.print(Panel(syntax, title=f"{method_name} [green]VALID JSON[/green]"))
            else:
                console.print(Panel(raw[:300], title=f"{method_name} [red]PARSE FAILED[/red]"))
        except Exception as e:
            logger.error("Error in %s: %s", method_name, e)

        console.input("\n[dim]Press Enter to continue...[/dim]")

    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
