"""
Structured Output & Prompt Scaffolding (Anthropic)

Demonstrates three approaches for getting structured JSON from Claude, progressing from
least to most reliable:
1. Prompt-based JSON — asking for JSON in the system prompt (can fail)
2. XML scaffolding — Anthropic-specific prompting technique (more reliable)
3. Native JSON schema — API-level schema enforcement via output_config (guaranteed)

Note: earlier versions of this tutorial also demonstrated assistant-message *prefill*
(seeding the assistant turn with `{` to force JSON). Claude 4.6 removed support for
assistant prefill — the conversation must end with a user message — so that step has
been dropped. See https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-6

All three methods extract the same product information from one description,
making it easy to compare reliability across techniques.
"""

import json

import anthropic
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from common import AnthropicTokenTracker, interactive_menu, setup_logging

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

    def extract_with_xml_scaffolding(self, description: str) -> str:
        """Use XML scaffolding — Anthropic-specific prompting technique."""
        schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
        system = (
            "You are a product data extraction assistant. Extract structured information "
            "from product descriptions as JSON matching the provided schema.\n\n"
            "Respond with ONLY the JSON object — no markdown fences, no commentary."
        )
        # XML tags help Claude parse the input structure
        user_content = (
            f"<schema>\n{schema_str}\n</schema>\n\n"
            f"<product_description>\n{description}\n</product_description>"
        )
        # Note: Claude 4.6 removed assistant-message prefill, so the previous
        # {"role": "assistant", "content": "{"} trick no longer works. XML tags
        # alone still significantly improve structural adherence.
        messages = [{"role": "user", "content": user_content}]
        return self._call(system, messages)

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
            result: str = response.parsed_output.model_dump_json(indent=2)
            return result
        return str(response.content[0].text)


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
    "A: Prompt-Based JSON",
    "B: XML Scaffolding",
    "C: Native JSON Schema",
]


def _run_method_a(console: Console, client: StructuredOutputClient) -> None:
    """Run the prompt-based JSON extraction method."""
    schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
    console.print("[dim]Embed the schema in the system prompt and ask for JSON output.[/dim]\n")
    prompt_a = (
        "**System prompt:**\n"
        "```\n"
        "You are a product data extraction assistant...\n"
        f"Output ONLY valid JSON matching this schema:\n{schema_str}\n"
        "No markdown, no explanation — just the JSON object.\n"
        "```\n\n"
        "**User message:** _(raw product description)_\n"
    )
    console.print(Markdown(prompt_a))

    try:
        raw = client.extract_json_prompted(PRODUCT_DESCRIPTION)
        _display_result(console, "A: Prompt-Based JSON", raw)
    except Exception as e:
        logger.error("Error in method A: %s", e)


def _run_method_b(console: Console, client: StructuredOutputClient) -> None:
    """Run the XML scaffolding extraction method."""
    schema_str = json.dumps(PRODUCT_SCHEMA_DESCRIPTION, indent=2)
    console.print(
        "[dim]Wrap input in XML tags so Claude clearly separates schema from data.[/dim]\n"
        "[dim]Assistant prefill used to pair with this technique, but Claude 4.6 "
        "removed support.[/dim]\n"
    )
    prompt_b = (
        "**System prompt:**\n"
        "```\n"
        "You are a product data extraction assistant...\n"
        "Respond with ONLY the JSON object.\n"
        "```\n\n"
        "**User message (XML-structured):**\n"
        "```xml\n"
        f"<schema>\n{schema_str}\n</schema>\n\n"
        "<product_description>\n(product description here)\n</product_description>\n"
        "```\n"
    )
    console.print(Markdown(prompt_b))

    try:
        raw = client.extract_with_xml_scaffolding(PRODUCT_DESCRIPTION)
        _display_result(console, "B: XML Scaffolding", raw)
    except Exception as e:
        logger.error("Error in method B: %s", e)


def _run_method_c(console: Console, client: StructuredOutputClient) -> None:
    """Run the native JSON schema extraction method."""
    console.print("[dim]API-level enforcement via Pydantic model — guaranteed valid JSON.[/dim]\n")
    prompt_c = (
        "**System prompt:**\n"
        "```\n"
        "You are a product data extraction assistant...\n"
        "```\n\n"
        "**User message:** _(raw product description)_\n\n"
        "**output_format (Pydantic model):**\n"
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
    console.print(Markdown(prompt_c))

    try:
        raw = client.extract_with_native_schema(PRODUCT_DESCRIPTION)
        _display_result(console, "C: Native Schema", raw)
    except Exception as e:
        logger.error("Error in method C: %s", e)


def main() -> None:
    """Run one product description through three structured output methods."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    client = StructuredOutputClient("claude-sonnet-4-6", token_tracker)

    header = Panel(
        "[bold cyan]Structured Output & Prompt Scaffolding[/bold cyan]\n\n"
        "Comparing 3 techniques for extracting structured JSON from free-form text:\n"
        "  A. Prompt-based JSON — ask for JSON in the system prompt\n"
        "  B. XML scaffolding — Anthropic-specific prompting technique\n"
        "  C. Native JSON schema — API-level enforcement via output_config (recommended)\n\n"
        f"[bold]Product Description:[/bold]\n{PRODUCT_DESCRIPTION}",
        title="Prompt Engineering — Anthropic",
    )

    methods = {
        METHOD_LABELS[0]: _run_method_a,
        METHOD_LABELS[1]: _run_method_b,
        METHOD_LABELS[2]: _run_method_c,
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
