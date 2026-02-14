"""
Structured Output & Prompt Scaffolding (OpenAI)

Demonstrates techniques for getting parseable structured output from OpenAI:
1. JSON via prompt instructions — asking for JSON in the system prompt
2. Markdown scaffolding — using structured sections to guide output
3. JSON schema enforcement — OpenAI's native structured output feature

Structured output is essential for agents that must parse LLM responses programmatically.
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

# Schema that the LLM should populate
TASK_SCHEMA = {
    "title": "string — concise task title",
    "priority": "HIGH | MEDIUM | LOW",
    "complexity": "integer 1-5",
    "required_tools": "list of tool names needed",
    "summary": "string — one sentence description",
}

# JSON schema for OpenAI's native structured output enforcement
TASK_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "task_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Concise task title"},
            "priority": {
                "type": "string",
                "enum": ["HIGH", "MEDIUM", "LOW"],
                "description": "Task priority level",
            },
            "complexity": {
                "type": "integer",
                "description": "Complexity score from 1 to 5",
            },
            "required_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of tool names needed",
            },
            "summary": {"type": "string", "description": "One sentence description"},
        },
        "required": ["title", "priority", "complexity", "required_tools", "summary"],
        "additionalProperties": False,
    },
}

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

    def extract_json_prompted(self, task_description: str) -> str:
        """Extract structured data by asking for JSON in the prompt."""
        schema_str = json.dumps(TASK_SCHEMA, indent=2)
        instructions = (
            "You are a task analysis assistant. Extract structured information from task "
            "descriptions.\n\n"
            f"Output ONLY valid JSON matching this schema:\n{schema_str}\n\n"
            "No markdown, no explanation — just the JSON object."
        )
        return self._call(instructions, task_description)

    def extract_with_scaffolding(self, task_description: str) -> str:
        """Use markdown sections to scaffold the input and guide the output."""
        schema_str = json.dumps(TASK_SCHEMA, indent=2)
        # OpenAI works well with markdown-structured prompts
        instructions = (
            "You are a task analysis assistant. You receive structured inputs and extract "
            "task data as JSON.\n\n"
            "Output ONLY valid JSON matching the provided schema. "
            "No markdown fences, no explanation."
        )
        user_input = (
            f"## Schema\n```json\n{schema_str}\n```\n\n"
            f"## Task Description\n{task_description}\n\n"
            "## Output\nExtract the task information as JSON:"
        )
        return self._call(instructions, user_input)

    def extract_with_schema(self, task_description: str) -> str:
        """Use OpenAI's native JSON schema enforcement — guaranteed valid JSON."""
        instructions = (
            "You are a task analysis assistant. Extract structured information from task "
            "descriptions. Populate all fields based on the task description."
        )
        # OpenAI's text format parameter enforces the schema at the API level
        return self._call(
            instructions,
            task_description,
            text={"format": TASK_JSON_SCHEMA},
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
    """Run sample tasks through three structured output methods."""
    console = Console()
    token_tracker = OpenAITokenTracker()
    client = StructuredOutputClient("gpt-4o", token_tracker)

    console.print(
        Panel(
            "[bold cyan]Structured Output & Prompt Scaffolding[/bold cyan]\n\n"
            "Comparing 3 techniques for extracting structured JSON from free-form text:\n"
            "  1. JSON via prompt instructions\n"
            "  2. Markdown scaffolding\n"
            "  3. JSON schema enforcement (OpenAI-specific)",
            title="Prompt Engineering — OpenAI",
        )
    )

    methods = {
        "Prompted JSON": client.extract_json_prompted,
        "Markdown Scaffolding": client.extract_with_scaffolding,
        "Schema Enforcement": client.extract_with_schema,
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
