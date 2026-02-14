"""
Structured Output & Prompt Scaffolding (Anthropic)

Demonstrates three approaches for getting structured JSON from Claude, progressing from
least to most reliable:
1. Prompt-based JSON — asking for JSON in the system prompt (can fail)
2. XML scaffolding + prefill — Anthropic-specific prompting techniques (more reliable)
3. Native JSON schema — API-level schema enforcement via output_config (guaranteed)

Structured output is essential for agents that must parse LLM responses programmatically.
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
TASK_SCHEMA_DESCRIPTION = {
    "title": "string — concise task title",
    "priority": "HIGH | MEDIUM | LOW",
    "complexity": "integer 1-5",
    "required_tools": "list of tool names needed",
    "summary": "string — one sentence description",
}


# Pydantic model for native structured output (machine-enforced)
class TaskExtraction(BaseModel):
    """Schema for extracting structured task data from free-form descriptions."""

    title: str
    priority: str
    complexity: int
    required_tools: list[str]
    summary: str


# Free-form task descriptions to extract structured data from
SAMPLE_TASKS = [
    (
        "We need to refactor the authentication module. The current JWT implementation "
        "has a token refresh bug that's causing users to get logged out randomly. It's "
        "affecting about 30% of our users and we need it fixed by Friday."
    ),
    (
        "Add a dark mode toggle to the settings page. It's a nice-to-have feature that "
        "a few users requested. Should be straightforward CSS changes with a theme context."
    ),
    (
        "The production database is running out of disk space. We need to archive old logs, "
        "optimize the indexes, and set up automated cleanup. This is urgent — we have "
        "maybe 48 hours before it starts failing."
    ),
]


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

    def extract_json_prompted(self, task_description: str) -> str:
        """Extract structured data by asking for JSON in the prompt — least reliable."""
        schema_str = json.dumps(TASK_SCHEMA_DESCRIPTION, indent=2)
        system = (
            "You are a task analysis assistant. Extract structured information from task "
            "descriptions.\n\n"
            f"Output ONLY valid JSON matching this schema:\n{schema_str}\n\n"
            "No markdown, no explanation — just the JSON object."
        )
        messages = [{"role": "user", "content": task_description}]
        return self._call(system, messages)

    def extract_with_prefill(self, task_description: str) -> str:
        """Use XML scaffolding + assistant prefill — Anthropic-specific technique."""
        schema_str = json.dumps(TASK_SCHEMA_DESCRIPTION, indent=2)
        system = (
            "You are a task analysis assistant. Extract structured information from task "
            "descriptions as JSON matching the provided schema."
        )
        # XML tags help Claude parse the input structure
        user_content = (
            f"<schema>\n{schema_str}\n</schema>\n\n"
            f"<task_description>\n{task_description}\n</task_description>"
        )
        # Prefill: start the assistant's response with '{' to force JSON output
        messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": "{"},
        ]
        raw = self._call(system, messages)
        # Reconstruct the full JSON since we prefilled the opening brace
        return "{" + raw

    def extract_with_native_schema(self, task_description: str) -> str:
        """Use native JSON schema enforcement via output_config — guaranteed valid JSON."""
        system = (
            "You are a task analysis assistant. Extract structured information from task "
            "descriptions."
        )
        messages = [{"role": "user", "content": task_description}]

        # Native structured output: API guarantees valid JSON matching the Pydantic schema
        response = self.client.beta.messages.parse(
            model=self.model,
            temperature=0.0,
            max_tokens=512,
            system=system,
            messages=messages,
            output_format=TaskExtraction,
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
    """Run sample tasks through three structured output methods."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    client = StructuredOutputClient("claude-sonnet-4-5-20250929", token_tracker)

    console.print(
        Panel(
            "[bold cyan]Structured Output & Prompt Scaffolding[/bold cyan]\n\n"
            "Comparing 3 techniques for extracting structured JSON from free-form text:\n"
            "  A. Prompt-based JSON — ask for JSON in the system prompt\n"
            "  B. XML scaffolding + prefill — Anthropic-specific prompting technique\n"
            "  C. Native JSON schema — API-level enforcement via output_config (recommended)",
            title="Prompt Engineering — Anthropic",
        )
    )

    methods = {
        "A: Prompt-Based JSON": client.extract_json_prompted,
        "B: XML + Prefill": client.extract_with_prefill,
        "C: Native Schema": client.extract_with_native_schema,
    }

    for i, task in enumerate(SAMPLE_TASKS, 1):
        console.print(f"\n[bold yellow]━━━ Task {i} ━━━[/bold yellow]")
        console.print(f"[dim]{task[:100]}...[/dim]\n")

        for method_name, method in methods.items():
            logger.info("Method: %s, Task: %d", method_name, i)
            try:
                raw = method(task)
                parsed = _try_parse_json(raw)

                if parsed:
                    formatted = json.dumps(parsed, indent=2)
                    syntax = Syntax(formatted, "json", theme="monokai")
                    console.print(Panel(syntax, title=f"{method_name} [green]VALID JSON[/green]"))
                else:
                    console.print(Panel(raw[:300], title=f"{method_name} [red]PARSE FAILED[/red]"))
            except Exception as e:
                logger.error("Error in %s: %s", method_name, e)

    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
