"""
Structured Output & Validation (Anthropic)

Demonstrates four production techniques for extracting reliable structured data from Claude,
progressing from basic to advanced:

1. Tool Use as Structured Output — force structured responses via tool_choice (simple + complex)
2. Native Structured Output — API-level constrained decoding (guaranteed valid)
3. Validation + Retry — self-healing extraction with error feedback loop
4. Batch Extraction — process multiple items in a single call

All techniques use the same real-world domain — support ticket analysis — so results
are directly comparable across methods.
"""

import json
from typing import Any, Literal

import anthropic
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field, ValidationError, model_validator
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from common import AnthropicTokenTracker, interactive_menu, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Pydantic models — progressive complexity
# ---------------------------------------------------------------------------


# Simple schema: flat classification
class TicketClassification(BaseModel):
    """Basic ticket classification with category, priority, and sentiment."""

    category: Literal["billing", "technical", "account", "feature_request", "general"]
    priority: Literal["critical", "high", "medium", "low"]
    sentiment: Literal["positive", "neutral", "negative", "frustrated"]
    summary: str = Field(description="One-sentence summary of the ticket")


# Complex schema: nested extraction
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

    # Custom business validation beyond what JSON schema can express
    @model_validator(mode="after")
    def check_escalation_consistency(self) -> "TicketAnalysis":
        """If escalation is required, a reason must be provided."""
        if self.requires_escalation and not self.escalation_reason:
            raise ValueError("escalation_reason is required when requires_escalation is True")
        return self


class TicketBatch(BaseModel):
    """Batch analysis of multiple tickets."""

    analyses: list[TicketAnalysis]
    batch_summary: str = Field(description="Overall summary of the batch")
    priority_distribution: dict[str, int] = Field(description="Count of tickets per priority level")


# ---------------------------------------------------------------------------
# Sample support tickets (easy → medium → hard)
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
        "Subject: API rate limit issues on Enterprise plan\n"
        "The API keeps returning 429 errors when I batch process more than 50 items. "
        "I'm on the Enterprise plan and the docs say the rate limit should be 1000/min. "
        "Could you also add a retry-after header to the response? That would help a lot. "
        "Using Python SDK v3.2.1."
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
# Core extractor class
# ---------------------------------------------------------------------------


class StructuredExtractor:
    """Extracts structured data from unstructured text using multiple techniques."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker

    # -- Technique 1: Tool Use as Structured Output --

    def extract_with_tool_use(
        self,
        text: str,
        model_class: type[BaseModel] = TicketClassification,
        tool_name: str = "classify_ticket",
        tool_description: str = "Classify a support ticket.",
    ) -> BaseModel | None:
        """Extract using tool_choice to force structured output via a tool definition."""
        tool = self._pydantic_to_tool(tool_name, tool_description, model_class)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": f"Analyze this ticket:\n\n{text}"}],
            )
            self.token_tracker.track(response.usage)

            for block in response.content:
                if block.type == "tool_use":
                    return model_class(**block.input)
        except Exception as e:
            logger.error("Tool use extraction failed: %s", e)
        return None

    # -- Technique 2: Native Structured Output (Constrained Decoding) --

    def extract_with_native_schema(self, text: str) -> TicketClassification | None:
        """Extract using Anthropic's native constrained decoding — guaranteed valid."""
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Analyze this ticket:\n\n{text}"}],
                output_config={"format": TicketClassification},
            )
            self.token_tracker.track(response.usage)

            result: TicketClassification | None = response.parsed_output
            if result:
                return result
        except Exception as e:
            logger.error("Native schema extraction failed: %s", e)
        return None

    # -- Technique 3: Validation + Retry (Self-Healing) --

    def extract_with_validation_retry(
        self, text: str, max_retries: int = 3
    ) -> TicketAnalysis | None:
        """Extract with validation loop — retry on failure with error feedback."""
        tool = self._pydantic_to_tool(
            name="analyze_ticket",
            description="Perform full analysis of a support ticket.",
            model=TicketAnalysis,
        )
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": f"Perform full analysis:\n\n{text}"}
        ]

        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    tools=[tool],
                    tool_choice={"type": "tool", "name": "analyze_ticket"},
                    messages=messages,
                )
                self.token_tracker.track(response.usage)

                for block in response.content:
                    if block.type == "tool_use":
                        raw = block.input
                        # Validate with Pydantic (includes custom business rules)
                        result = TicketAnalysis(**raw)
                        logger.info("Attempt %d: validation passed", attempt)
                        return result

            except ValidationError as e:
                logger.warning("Attempt %d: validation failed — %s", attempt, e)
                if attempt < max_retries:
                    # Feed the error back to the LLM for correction
                    messages = [
                        {"role": "user", "content": f"Perform full analysis:\n\n{text}"},
                        {"role": "assistant", "content": response.content},
                        {
                            "role": "user",
                            "content": (
                                f"The output failed validation:\n{e}\n\n"
                                "Please fix the issues and try again. Key rules:\n"
                                "- If requires_escalation is true, escalation_reason must "
                                "be a non-empty string\n"
                                "- All enum values must match exactly"
                            ),
                        },
                    ]
            except Exception as e:
                logger.error("Attempt %d: unexpected error — %s", attempt, e)
                break

        logger.error("All %d attempts failed", max_retries)
        return None

    # -- Technique 4: Batch Extraction --

    def extract_batch(self, texts: list[str]) -> TicketBatch | None:
        """Extract structured data from multiple tickets in a single call."""
        tool = self._pydantic_to_tool(
            name="batch_analyze",
            description="Analyze multiple support tickets and provide batch summary.",
            model=TicketBatch,
        )
        numbered_tickets = "\n\n".join(
            f"--- TICKET {i + 1} ---\n{text}" for i, text in enumerate(texts)
        )
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[tool],
                tool_choice={"type": "tool", "name": "batch_analyze"},
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Analyze all {len(texts)} tickets below and provide a "
                            f"batch analysis:\n\n{numbered_tickets}"
                        ),
                    }
                ],
            )
            self.token_tracker.track(response.usage)

            for block in response.content:
                if block.type == "tool_use":
                    return TicketBatch(**block.input)
        except Exception as e:
            logger.error("Batch extraction failed: %s", e)
        return None

    # -- Helpers --

    def _pydantic_to_tool(
        self, name: str, description: str, model: type[BaseModel]
    ) -> dict[str, Any]:
        """Convert any Pydantic model to an Anthropic tool definition."""
        return {
            "name": name,
            "description": description,
            "input_schema": model.model_json_schema(),
        }


# ---------------------------------------------------------------------------
# Display helpers (Rich UI)
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
# Menu handlers
# ---------------------------------------------------------------------------

TECHNIQUE_LABELS = [
    "1: Tool Use as Structured Output (Simple + Complex)",
    "2: Native Structured Output (Constrained Decoding)",
    "3: Validation + Retry (Self-Healing)",
    "4: Batch Extraction (Multiple Items)",
]


def _run_tool_use(console: Console, extractor: StructuredExtractor) -> None:
    """Technique 1: Extract using tool_choice — simple and complex schemas."""
    console.print(
        "[dim]Force structured output by defining a tool whose input_schema IS the "
        "desired output schema, then using tool_choice to invoke it.[/dim]\n"
    )
    console.print(
        Markdown(
            "**How it works:** Define a tool → set `tool_choice` to force it → "
            "extract `block.input` as structured data.\n\n"
            "**Key insight:** Use `model.model_json_schema()` to generate tool schemas "
            "from Pydantic models — never hand-write JSON schemas for complex structures.\n\n"
            "**Reliability:** High — tool inputs are schema-validated by the API.\n"
        )
    )

    # Part A: Simple flat schema
    console.print("[bold]Part A: Simple schema[/bold] — `TicketClassification` (flat, 4 fields)\n")
    ticket_simple = SAMPLE_TICKETS[0]
    console.print(Panel(ticket_simple, title="Input Ticket (Simple)"))

    result_simple = extractor.extract_with_tool_use(ticket_simple)
    _display_result(console, "Simple Schema Extraction", result_simple)

    # Part B: Complex nested schema
    console.print(
        "\n[bold]Part B: Complex schema[/bold] — `TicketAnalysis` "
        "(nested: classification + entities + action items, 10+ fields)\n"
    )
    ticket_complex = SAMPLE_TICKETS[2]
    console.print(Panel(ticket_complex, title="Input Ticket (Complex)"))

    result_complex = extractor.extract_with_tool_use(
        ticket_complex,
        model_class=TicketAnalysis,
        tool_name="analyze_ticket",
        tool_description="Perform full analysis of a support ticket.",
    )
    _display_result(console, "Complex Schema Extraction", result_complex)


def _run_native_schema(console: Console, extractor: StructuredExtractor) -> None:
    """Technique 2: Extract using native constrained decoding."""
    console.print(
        "[dim]Use Anthropic's native structured output — the model literally cannot "
        "produce invalid JSON. Uses constrained decoding at the decoder level.[/dim]\n"
    )
    console.print(
        Markdown(
            "**How it works:** Pass a Pydantic model as `output_config` → API guarantees "
            "the response matches the schema exactly.\n\n"
            "**Schema:** `TicketClassification` (flat, 4 fields)\n\n"
            "**Reliability:** Guaranteed — decoder-level enforcement, zero parsing errors.\n"
        )
    )

    ticket = SAMPLE_TICKETS[0]
    console.print(Panel(ticket, title="Input Ticket"))

    result = extractor.extract_with_native_schema(ticket)
    _display_result(console, "Native Schema Extraction", result)


def _run_validation_retry(console: Console, extractor: StructuredExtractor) -> None:
    """Technique 3: Self-healing extraction with validation + retry."""
    console.print(
        "[dim]When schema validation isn't enough — add custom business rules. "
        "On failure, feed the validation error back to the LLM for self-correction.[/dim]\n"
    )
    console.print(
        Markdown(
            "**How it works:** Extract → validate with Pydantic (including custom "
            "`@model_validator` rules) → on failure, send error back to LLM → retry.\n\n"
            "**Custom rule:** If `requires_escalation` is True, `escalation_reason` "
            "must be provided (not expressible in JSON Schema alone).\n\n"
            "**Max retries:** 3 attempts with error accumulation.\n"
        )
    )

    # Use ticket 3 — likely to require escalation (enterprise evaluation, blocker)
    ticket = SAMPLE_TICKETS[2]
    console.print(Panel(ticket, title="Input Ticket (Requires Escalation)"))

    result = extractor.extract_with_validation_retry(ticket)
    _display_result(console, "Validation + Retry Extraction", result)


def _run_batch(console: Console, extractor: StructuredExtractor) -> None:
    """Technique 4: Batch extraction from multiple items."""
    console.print(
        "[dim]Process multiple tickets in a single API call. The model extracts "
        "structured data for each and provides a batch summary.[/dim]\n"
    )
    console.print(
        Markdown(
            "**How it works:** Send all tickets in one prompt → extract a `TicketBatch` "
            "with `list[TicketAnalysis]` + summary + priority distribution.\n\n"
            "**Use case:** Production data pipelines processing ticket queues.\n\n"
            "**Trade-off:** Single call (cheaper) vs per-item calls (more reliable). "
            "Batch works well for 3-10 items; beyond that, parallelize individual calls.\n"
        )
    )

    for i, ticket in enumerate(SAMPLE_TICKETS):
        console.print(Panel(ticket, title=f"Ticket {i + 1}"))

    result = extractor.extract_batch(SAMPLE_TICKETS)
    _display_result(console, "Batch Extraction", result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run support ticket analysis through four structured output techniques."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    extractor = StructuredExtractor(MODEL, token_tracker)

    header = Panel(
        "[bold cyan]Structured Output & Validation[/bold cyan]\n\n"
        "Four techniques for extracting reliable structured data from Claude:\n"
        "  1. Tool Use — force structured output via tool_choice (simple + complex)\n"
        "  2. Native Schema — constrained decoding (guaranteed valid)\n"
        "  3. Validation + Retry — self-healing with error feedback\n"
        "  4. Batch Extraction — multiple items in one call\n\n"
        "[bold]Domain:[/bold] Support ticket analysis (classification, entities, actions)",
        title="Advanced Techniques — Anthropic",
    )

    handlers = {
        TECHNIQUE_LABELS[0]: _run_tool_use,
        TECHNIQUE_LABELS[1]: _run_native_schema,
        TECHNIQUE_LABELS[2]: _run_validation_retry,
        TECHNIQUE_LABELS[3]: _run_batch,
    }

    try:
        while True:
            selection = interactive_menu(
                console,
                TECHNIQUE_LABELS,
                title="Select a Technique",
                header=header,
            )
            if not selection:
                break

            console.print(f"\n[bold yellow]━━━ {selection} ━━━[/bold yellow]\n")

            try:
                handlers[selection](console, extractor)
            except Exception as e:
                logger.error("Technique error: %s", e)

            token_tracker.report()
            token_tracker.reset()

            console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()
