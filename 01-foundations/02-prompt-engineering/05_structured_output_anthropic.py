"""
Structured Output & Prompt Scaffolding (Anthropic)

Demonstrates three approaches for getting structured JSON from Claude, progressing from
least to most reliable:
1. Prompt-based JSON — asking for JSON in the system prompt (can fail)
2. XML scaffolding + prefill — Anthropic-specific prompting techniques (more reliable)
3. Native JSON schema — API-level schema enforcement via output_config (guaranteed)

All three methods extract the same product information from one description,
making it easy to compare reliability across techniques.
"""

import json

import anthropic
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from common import AnthropicTokenTracker, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# Schema description for prompt-based methods (human-readable)
PRODUCT_SCHEMA_DESCRIPTION = {
    "name": "string — product name",
    "category": "string — product category (e.g., Electronics, Clothing)",
    "price": "number — price in USD",
    "features": "list of strings — key product features",
    "in_stock": "boolean — whether the product is currently available",
}


# Pydantic model for native structured output (machine-enforced)
class ProductExtraction(BaseModel):
    """Schema for extracting structured product data from free-form descriptions."""

    name: str
    category: str
    price: float
    features: list[str]
    in_stock: bool


# Single product description — all three methods extract from this same input
PRODUCT_DESCRIPTION = (
    "The UltraSound Pro X1 wireless noise-cancelling headphones deliver studio-quality "
    "audio with 40mm custom drivers and adaptive ANC. Features include 30-hour battery "
    "life, multipoint Bluetooth 5.3 for connecting two devices simultaneously, and a "
    "foldable design with a premium carrying case. Available now at $249.99. "
    "Currently in stock and shipping within 24 hours."
)


class StructuredOutputClient:
    """Demonstrates structured output techniques with Anthropic's API."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker

    def _call(self, system: str, messages: list[dict], **kwargs: object) -> str:
        """Make an API call and track tokens."""
        response = self.client.messages.create(
            model=self.model,
            temperature=0.0,
            max_tokens=512,
            system=system,
            messages=messages,
            **kwargs,
        )
        self.token_tracker.track(response.usage)
        return str(response.content[0].text)

    def extract_json_prompted(self, description: str) -> str:
        """Extract structured data by asking for JSON in the prompt — least reliable."""
        schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
        system = (
            "You are a product data extraction assistant. Extract structured information "
            "from product descriptions.\n\n"
            f"Output ONLY valid JSON matching this schema:\n{schema_str}\n\n"
            "No markdown, no explanation — just the JSON object."
        )
        messages = [{"role": "user", "content": description}]
        return self._call(system, messages)

    def extract_with_prefill(self, description: str) -> str:
        """Use XML scaffolding + assistant prefill — Anthropic-specific technique."""
        schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
        system = (
            "You are a product data extraction assistant. Extract structured information "
            "from product descriptions as JSON matching the provided schema."
        )
        # XML tags help Claude parse the input structure
        user_content = (
            f"<schema>\n{schema_str}\n</schema>\n\n"
            f"<product_description>\n{description}\n</product_description>"
        )
        # Prefill: start the assistant's response with '{' to force JSON output
        messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": "{"},
        ]
        raw = self._call(system, messages)
        # Reconstruct the full JSON since we prefilled the opening brace
        return "{" + raw

    def extract_with_native_schema(self, description: str) -> str:
        """Use native JSON schema enforcement via output_config — guaranteed valid JSON."""
        system = (
            "You are a product data extraction assistant. Extract structured information "
            "from product descriptions."
        )
        messages = [{"role": "user", "content": description}]

        # Native structured output: API guarantees valid JSON matching the Pydantic schema
        response = self.client.beta.messages.parse(
            model=self.model,
            temperature=0.0,
            max_tokens=512,
            system=system,
            messages=messages,
            output_format=ProductExtraction,
        )
        self.token_tracker.track(response.usage)

        # parsed_output is a validated Pydantic model instance
        if response.parsed_output:
            return response.parsed_output.model_dump_json(indent=2)
        return str(response.content[0].text)


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
    token_tracker = AnthropicTokenTracker()
    client = StructuredOutputClient("claude-sonnet-4-5-20250929", token_tracker)

    console.print(
        Panel(
            "[bold cyan]Structured Output & Prompt Scaffolding[/bold cyan]\n\n"
            "Comparing 3 techniques for extracting structured JSON from free-form text:\n"
            "  A. Prompt-based JSON — ask for JSON in the system prompt\n"
            "  B. XML scaffolding + prefill — Anthropic-specific prompting technique\n"
            "  C. Native JSON schema — API-level enforcement via output_config (recommended)\n\n"
            "All three extract from the same product description for easy comparison.",
            title="Prompt Engineering — Anthropic",
        )
    )

    console.print("\n[bold yellow]━━━ Product Description ━━━[/bold yellow]")
    console.print(Panel(PRODUCT_DESCRIPTION, border_style="dim"))

    methods = {
        "A: Prompt-Based JSON": client.extract_json_prompted,
        "B: XML + Prefill": client.extract_with_prefill,
        "C: Native Schema": client.extract_with_native_schema,
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
