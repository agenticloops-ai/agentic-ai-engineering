"""
Skills (OpenAI)

Same filesystem Agent Skills as the Anthropic version, driven through the OpenAI
Responses API. Skills are pure convention — a SKILL.md catalog plus two tools —
so the pattern is identical across providers; only the loop plumbing differs.

Progressive disclosure, three tiers:
  1. Catalog     — every skill's name + description, injected into the instructions
  2. load_skill  — returns the full SKILL.md body for one skill
  3. read_skill_file — reads a file bundled alongside a skill (e.g. a template)
"""

import json
from pathlib import Path
from typing import Any

import yaml
from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common.logging_config import setup_logging
from common.token_tracking import OpenAITokenTracker

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

SKILLS_DIR = Path(__file__).parent / "skills"


def parse_skill(skill_md: Path) -> tuple[dict[str, str], str]:
    """Split a SKILL.md into its YAML front-matter dict and Markdown body."""
    text = skill_md.read_text()
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        meta = yaml.safe_load(front) or {}
        return meta, body.strip()
    return {}, text.strip()


def discover_skills(skills_dir: Path) -> dict[str, dict[str, str]]:
    """Scan the skills directory and return {name: {description, dir}} for the catalog."""
    catalog: dict[str, dict[str, str]] = {}
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        meta, _ = parse_skill(skill_md)
        name = meta.get("name", skill_md.parent.name)
        catalog[name] = {
            "description": meta.get("description", ""),
            "dir": skill_md.parent.name,
        }
    return catalog


def build_catalog_prompt(catalog: dict[str, dict[str, str]]) -> str:
    """Render the always-loaded skill catalog for the instructions (tier 1)."""
    lines = [f"- {name}: {info['description']}" for name, info in catalog.items()]
    return "\n".join(lines)


def safe_skill_path(catalog: dict[str, dict[str, str]], skill: str, relative: str) -> Path:
    """Resolve a bundled skill file, refusing paths that escape the skill directory."""
    base = (SKILLS_DIR / catalog[skill]["dir"]).resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"Path traversal blocked: {relative}")
    return target


TOOLS = [
    {
        "type": "function",
        "name": "load_skill",
        "description": "Load the full instructions for a skill by name (tier 2 disclosure).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The skill name from the catalog"}
            },
            "additionalProperties": False,
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "read_skill_file",
        "description": "Read a file bundled alongside a skill, e.g. a referenced template.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "The skill name"},
                "path": {"type": "string", "description": "File path relative to the skill dir"},
            },
            "additionalProperties": False,
            "required": ["skill", "path"],
        },
    },
]


class SkillAgent:
    """Agent that discovers filesystem skills and loads them on demand."""

    def __init__(self, model: str = "gpt-4.1"):
        self.client = OpenAI()
        self.model = model
        self.max_iterations = 10
        self.token_tracker = OpenAITokenTracker()
        self.catalog = discover_skills(SKILLS_DIR)
        self.instructions = (
            "You are an assistant with access to skills — specialized capabilities you "
            "load only when relevant. Available skills:\n\n"
            f"{build_catalog_prompt(self.catalog)}\n\n"
            "When a task matches a skill, call load_skill to get its full instructions, "
            "then follow them. Some skills reference bundled files — read those with "
            "read_skill_file before acting."
        )

    def execute_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        """Dispatch a skill tool call (tiers 2 and 3 of progressive disclosure)."""
        try:
            if name == "load_skill":
                skill = tool_input["name"]
                if skill not in self.catalog:
                    return f"Error: unknown skill '{skill}'"
                _, body = parse_skill(SKILLS_DIR / self.catalog[skill]["dir"] / "SKILL.md")
                return body
            if name == "read_skill_file":
                skill = tool_input["skill"]
                if skill not in self.catalog:
                    return f"Error: unknown skill '{skill}'"
                return safe_skill_path(self.catalog, skill, tool_input["path"]).read_text()
        except Exception as e:
            return f"Error: {e}"
        return f"Unknown tool: {name}"

    def run(self, task: str) -> str:
        """Execute the agent loop, letting the model pull in skills as needed."""
        logger.info(f"Task: {task}")
        input_messages: list[Any] = [{"role": "user", "content": task}]
        previous_response_id: str | None = None

        for iteration in range(self.max_iterations):
            logger.info(f"--- Iteration {iteration + 1} ---")
            response = self.client.responses.create(
                model=self.model,
                tools=TOOLS,
                instructions=self.instructions,
                input=input_messages,
                **({"previous_response_id": previous_response_id} if previous_response_id else {}),
            )
            if response.usage:
                self.token_tracker.track(response.usage)
            if response.output_text:
                logger.info(f"🤖 Agent: {response.output_text}")

            function_calls = [o for o in response.output if o.type == "function_call"]
            if not function_calls:
                return response.output_text or "Done"

            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments)
                except json.JSONDecodeError as e:
                    args = {}
                    logger.error(f"Invalid tool arguments: {e}")
                logger.info(f"🧩 Skill tool: {call.name}({json.dumps(args)})")
                result = self.execute_tool(call.name, args)
                logger.info(f"📋 Result: {result[:100]}{'...' if len(result) > 100 else ''}")
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps({"result": result}),
                    }
                )

            previous_response_id = response.id
            input_messages = tool_outputs

        return "Max iterations reached"


def main() -> None:
    """Interactive CLI demonstrating on-demand skill loading."""
    console = Console()
    agent = SkillAgent()
    console.print(
        Panel(
            "This agent loads skills only when needed.\n\n"
            f"Discovered skills: {', '.join(agent.catalog) or '(none)'}\n\n"
            "Try:\n"
            "  - Review the code in 02_skills_openai.py\n"
            "  - Add a changelog entry for version 1.2.0 adding skill support\n\n"
            "Type 'quit' to exit.",
            title="Skills (OpenAI)",
        )
    )

    try:
        while True:
            console.print("\n[bold green]You:[/bold green] ", end="")
            user_input = input().strip()
            if user_input.lower() in ("exit", "quit", "q", ""):
                console.print("\n[yellow]Ending session...[/yellow]")
                break
            response = agent.run(user_input)
            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(response))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    agent.token_tracker.report()


if __name__ == "__main__":
    main()
