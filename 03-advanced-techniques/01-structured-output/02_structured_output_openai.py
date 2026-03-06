"""
Structured Output & Validation (OpenAI)

Shows how the same structured output goal works with OpenAI's API. OpenAI uses `text.format`
with strict JSON schema enforcement — conceptually equivalent to Anthropic's `output_config`
(both use constrained decoding), but with a different API surface.

Demonstrates both simple and complex schemas using the same support ticket domain as the
Anthropic script. The key OpenAI-specific detail: strict mode requires `additionalProperties:
false` and all properties marked `required` at every nested object level.

Run the Anthropic script first to see the primary techniques, then run this to compare.
"""

import json
from typing import Literal

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from common import OpenAITokenTracker, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

MODEL = "gpt-4.1"


# ---------------------------------------------------------------------------
# Pydantic models — same schemas as Anthropic script
# ---------------------------------------------------------------------------


class TicketClassification(BaseModel):
    """Basic ticket classification with category, priority, and sentiment."""

    category: Literal["billing", "technical", "account", "feature_request", "general"]
    priority: Literal["critical", "high", "medium", "low"]
    sentiment: Literal["positive", "neutral", "negative", "frustrated"]
    summary: str = Field(description="One-sentence summary of the ticket")


class Entity(BaseModel):
    """An entity mentioned in the ticket."""

    name: str = Field(description="Entity name as mentioned in the ticket")
    type: Literal["product", "feature", "error_code", "account_id", "person"]
    context: str = Field(description="Brief context of how it was mentioned")


class ActionItem(BaseModel):
    """A recommended action to resolve the ticket."""

    action: str = Field(description="Specific action to take")
    assignee: Literal["support", "engineering", "billing", "account_manager"]
    urgency: Literal["immediate", "next_business_day", "backlog"]


class TicketAnalysis(BaseModel):
    """Full ticket analysis with classification, entities, and action items."""

    classification: TicketClassification
    entities: list[Entity]
    action_items: list[ActionItem]
    requires_escalation: bool
    escalation_reason: str | None = None
    customer_tier: Literal["free", "pro", "enterprise"] | None = None


# ---------------------------------------------------------------------------
# Sample tickets (same as Anthropic script)
# ---------------------------------------------------------------------------

SAMPLE_TICKETS = [
    (
        "Subject: Double charged for Pro subscription\n"
        "Hi, I was charged twice for my Pro subscription this month — $49.99 on Jan 3rd "
        "and again on Jan 5th. My account ID is ACC-78234. This is the third time this "
        "has happened and I'm really frustrated. Please refund the duplicate charge ASAP. "
        "If this isn't resolved today I'm cancelling my subscription."
    ),
    (
        "Subject: SSO blocker during enterprise evaluation\n"
        "We're evaluating your product for our team of 200 engineers. The SSO integration "
        "with Okta worked great but we hit a blocker — the SCIM provisioning endpoint returns "
        "a 500 error when syncing groups with more than 50 members (error: SCIM-ERR-4012). "
        "Also, is there a way to get volume pricing? Our current Acme Corp contract is up "
        "for renewal next month. Contact: Sarah Chen, VP Engineering."
    ),
]

SYSTEM_PROMPT = (
    "You are a support ticket analysis system. Analyze customer support tickets "
    "and extract structured data. Be precise with classifications and extract all "
    "relevant entities and action items."
)


# ---------------------------------------------------------------------------
# Schema conversion helper
# ---------------------------------------------------------------------------


def _pydantic_to_openai_schema(name: str, model: type[BaseModel]) -> dict:
    """Convert a Pydantic model to OpenAI's response_format JSON schema definition.

    OpenAI strict mode has specific requirements that differ from standard JSON Schema:
    - `additionalProperties: false` at every object level
    - All properties must be listed in `required` (even optional ones)
    These constraints are applied recursively to handle nested models.
    """
    schema = model.model_json_schema()
    _add_strict_constraints(schema)
    return {
        "type": "json_schema",
        "name": name,
        "strict": True,
        "schema": schema,
    }


def _add_strict_constraints(schema: dict) -> None:
    """Recursively add additionalProperties: false to all object types in schema."""
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        if "properties" in schema:
            schema.setdefault("required", list(schema["properties"].keys()))
    for value in schema.values():
        if isinstance(value, dict):
            _add_strict_constraints(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _add_strict_constraints(item)
    # Handle $defs (Pydantic puts nested model schemas here)
    if "$defs" in schema:
        for defn in schema["$defs"].values():
            _add_strict_constraints(defn)


# ---------------------------------------------------------------------------
# Core extractor class
# ---------------------------------------------------------------------------


class StructuredExtractor:
    """Extracts structured data using OpenAI's native schema enforcement."""

    def __init__(self, model: str, token_tracker: OpenAITokenTracker):
        self.client = OpenAI()
        self.model = model
        self.token_tracker = token_tracker

    def extract(
        self,
        text: str,
        model_class: type[BaseModel] = TicketClassification,
        schema_name: str = "ticket_classification",
    ) -> BaseModel | None:
        """Extract structured data using OpenAI's text.format with strict JSON schema."""
        schema = _pydantic_to_openai_schema(schema_name, model_class)
        try:
            response = self.client.responses.create(
                model=self.model,
                temperature=0.0,
                max_output_tokens=2048,
                instructions=SYSTEM_PROMPT,
                input=f"Analyze this ticket:\n\n{text}",
                text={"format": schema},
            )
            if hasattr(response, "usage") and response.usage:
                self.token_tracker.track(response.usage)

            raw_json = response.output_text
            if raw_json:
                data = json.loads(raw_json)
                return model_class(**data)
        except Exception as e:
            logger.error("Schema extraction failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Display helper
# ---------------------------------------------------------------------------


def _display_result(console: Console, title: str, result: BaseModel | None) -> None:
    """Display a Pydantic model as formatted JSON."""
    if result:
        formatted = json.dumps(result.model_dump(), indent=2, default=str)
        syntax = Syntax(formatted, "json", theme="monokai")
        console.print(Panel(syntax, title=f"{title} [green]SUCCESS[/green]"))
    else:
        console.print(Panel("[red]Extraction failed[/red]", title=title))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run support ticket analysis through OpenAI's structured output."""
    console = Console()
    token_tracker = OpenAITokenTracker()
    extractor = StructuredExtractor(MODEL, token_tracker)

    console.print(
        Panel(
            "[bold cyan]Structured Output — OpenAI Comparison[/bold cyan]\n\n"
            "OpenAI's `text.format` with strict JSON schema is conceptually the same as\n"
            "Anthropic's `output_config` — both use constrained decoding to guarantee\n"
            "valid output. The difference is API surface, not mechanism.\n\n"
            "[bold]OpenAI-specific detail:[/bold] Strict mode requires "
            "`additionalProperties: false`\n"
            "and all properties in `required` at every nested object level.",
            title="Advanced Techniques — OpenAI",
        )
    )

    console.print(
        Markdown(
            "**Anthropic vs OpenAI — what's actually different:**\n\n"
            "| Aspect | Anthropic | OpenAI |\n"
            "|--------|-----------|--------|\n"
            "| Constrained decoding | `output_config=Model` | `text.format` with strict schema |\n"
            "| Tool-based extraction | `tool_use` + `tool_choice` | Also supported (not shown) |\n"
            "| Pydantic integration | Pass model directly | Need schema conversion helper |\n"
            "| Strict mode requirement | None | `additionalProperties: false` everywhere |\n\n"
            "Both guarantee valid JSON — same reliability, different API.\n"
        )
    )

    # Part A: Simple flat schema
    console.print(
        "\n[bold]Part A: Simple schema[/bold] — `TicketClassification` (flat, 4 fields)\n"
    )
    ticket_simple = SAMPLE_TICKETS[0]
    console.print(Panel(ticket_simple, title="Input Ticket (Simple)"))

    result_simple = extractor.extract(ticket_simple)
    _display_result(console, "Simple Schema Extraction", result_simple)

    token_tracker.report()
    token_tracker.reset()

    # Part B: Complex nested schema
    console.print(
        "\n[bold]Part B: Complex schema[/bold] — `TicketAnalysis` "
        "(nested: classification + entities + action items)\n"
    )
    console.print(
        "[dim]Same Pydantic models as the Anthropic script — only the conversion "
        "layer differs (adding strict constraints recursively).[/dim]\n"
    )
    ticket_complex = SAMPLE_TICKETS[1]
    console.print(Panel(ticket_complex, title="Input Ticket (Complex)"))

    result_complex = extractor.extract(
        ticket_complex,
        model_class=TicketAnalysis,
        schema_name="ticket_analysis",
    )
    _display_result(console, "Complex Schema Extraction", result_complex)

    token_tracker.report()


if __name__ == "__main__":
    main()
