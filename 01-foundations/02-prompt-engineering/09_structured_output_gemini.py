"""
Structured Output & Prompt Scaffolding (Gemini)

Demonstrates three approaches for getting structured JSON from Gemini, progressing from
least to most reliable:
1. Prompt-based JSON — asking for JSON in the system prompt (can fail)
2. Markdown scaffolding — using structured sections to guide output
3. Native JSON schema — API-level schema enforcement via response_schema (guaranteed)

All three methods extract the same product information from one description,
making it easy to compare reliability across techniques.
"""

import json

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from common import GeminiTokenTracker, interactive_menu, setup_logging

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
    """Demonstrates structured output techniques with Gemini's API."""

    def __init__(self, model: str, token_tracker: GeminiTokenTracker):
        self.client = genai.Client()
        self.model = model
        self.token_tracker = token_tracker

    def _call(self, config: types.GenerateContentConfig, user_input: str) -> str:
        """Make an API call and track tokens."""
        response = self.client.models.generate_content(
            model=self.model,
            contents=user_input,
            config=config,
        )
        if response.usage_metadata:
            self.token_tracker.track(response.usage_metadata)
        return (response.text or "").strip()

    def extract_json_prompted(self, description: str) -> str:
        """Extract structured data by asking for JSON in the prompt — least reliable."""
        schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
        system = (
            "You are a product data extraction assistant. Extract structured information "
            "from product descriptions.\n\n"
            f"Output ONLY valid JSON matching this schema:\n{schema_str}\n\n"
            "No markdown, no explanation — just the JSON object."
        )
        
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            max_output_tokens=512,
        )
        return self._call(config, description)

    def extract_with_scaffolding(self, description: str) -> str:
        """Use markdown scaffolding to guide the model's output structure."""
        schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
        system = (
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
        
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            max_output_tokens=512,
        )
        return self._call(config, user_input)

    def extract_with_native_schema(self, description: str) -> str:
        """Use native JSON schema enforcement via response_schema — guaranteed valid JSON."""
        system = (
            "You are a product data extraction assistant. Extract structured information "
            "from product descriptions. Populate all fields based on the description."
        )
        
        # Native structured output: API guarantees valid JSON matching the Pydantic schema
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            max_output_tokens=512,
            response_mime_type="application/json",
            response_schema=ProductExtraction,
        )
        
        return self._call(config, description)


def _try_parse_json(raw: str) -> dict | None:
    """Attempt to parse JSON, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed: dict[str, object] = json.loads(text)
        return parsed
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


METHOD_LABELS = [
    "1: Prompted JSON",
    "2: Markdown Scaffolding",
    "3: Native JSON Schema",
]


def _run_method_1(console: Console, client: StructuredOutputClient) -> None:
    """Run the prompted JSON extraction method."""
    schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
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

    try:
        raw = client.extract_json_prompted(PRODUCT_DESCRIPTION)
        _display_result(console, "Prompted JSON", raw)
    except Exception as e:
        logger.error("Error in method 1: %s", e)


def _run_method_2(console: Console, client: StructuredOutputClient) -> None:
    """Run the markdown scaffolding extraction method."""
    schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
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

    try:
        raw = client.extract_with_scaffolding(PRODUCT_DESCRIPTION)
        _display_result(console, "Markdown Scaffolding", raw)
    except Exception as e:
        logger.error("Error in method 2: %s", e)


def _run_method_3(console: Console, client: StructuredOutputClient) -> None:
    """Run the native JSON schema extraction method."""
    console.print("[dim]API-level enforcement via Pydantic model — guaranteed valid JSON.[/dim]\n")
    prompt_3 = (
        "**Instructions:**\n"
        "```\n"
        "You are a product data extraction assistant...\n"
        "Populate all fields based on the description.\n"
        "```\n\n"
        "**Input:** _(raw product description)_\n\n"
        "**response_schema (Pydantic model):**\n"
        "```python\n"
        "class ProductExtraction(BaseModel):\n"
        "    name: str\n"
        "    category: str\n"
        "    price: float\n"
        "    features: list[str]\n"
        "    in_stock: bool\n"
        "```\n\n"
        "_The API guarantees the response conforms to this schema — no parsing needed._\n"
    )
    console.print(Markdown(prompt_3))

    try:
        raw = client.extract_with_native_schema(PRODUCT_DESCRIPTION)
        _display_result(console, "Native Schema", raw)
    except Exception as e:
        logger.error("Error in method 3: %s", e)


def main() -> None:
    """Run one product description through three structured output methods."""
    console = Console()
    token_tracker = GeminiTokenTracker()
    client = StructuredOutputClient("gemini-2.5-flash", token_tracker)

    header = Panel(
        "[bold cyan]Structured Output & Prompt Scaffolding[/bold cyan]\n\n"
        "Comparing 3 techniques for extracting structured JSON from free-form text:\n"
        "  1. JSON via prompt instructions\n"
        "  2. Markdown scaffolding\n"
        "  3. Native JSON schema (Gemini-specific)\n\n"
        f"[bold]Product Description:[/bold]\n{PRODUCT_DESCRIPTION}",
        title="Prompt Engineering — Gemini",
    )

    methods = {
        METHOD_LABELS[0]: _run_method_1,
        METHOD_LABELS[1]: _run_method_2,
        METHOD_LABELS[2]: _run_method_3,
    }

    try:
        while True:
            selection = interactive_menu(
                console,
                METHOD_LABELS,
                title="Select a Method",
                header=header,
            )
            if not selection:
                break

            console.print(f"\n[bold yellow]━━━ {selection} ━━━[/bold yellow]")

            try:
                methods[selection](console, client)
            except Exception as e:
                logger.error("Method error: %s", e)

            token_tracker.report()
            token_tracker.reset()

            console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()