"""
Agent Skills (Anthropic)

Demonstrates filesystem-based Agent Skills with three-tier progressive disclosure:

- Tier 1 (catalog): skill names and descriptions sit in the system prompt, always loaded
- Tier 2 (instructions): the agent calls load_skill to pull in a SKILL.md body on demand
- Tier 3 (bundled files): the agent calls read_skill_file for references and templates

The base prompt stays lean no matter how many skills you install, because a skill only
costs tokens once the agent decides it needs one.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import yaml
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
EFFORT = "medium"
MAX_ITERATIONS = 10

# Re-run a safety-declined turn on a fallback model instead of ending the loop
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SKILLS_DIR = Path(__file__).parent / "skills"
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_DESCRIPTION_CHARS = 1024

BASE_SYSTEM_PROMPT = """You are a capable assistant with access to specialized skills.

A skill is a folder of expert instructions. The catalog below lists what is available.
When a task matches a skill's description, call load_skill before doing the work, then follow
its instructions. Those instructions may point to bundled files: read them with read_skill_file
only when the task needs them. If no skill applies, answer directly without loading anything.

<available_skills>
{catalog}
</available_skills>"""

TOOLS: list[Any] = [
    {
        "name": "load_skill",
        "description": "Load the full instructions of a skill from the catalog.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name from the catalog"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "read_skill_file",
        "description": "Read a file bundled with a skill, using a path relative to its folder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "Skill name from the catalog"},
                "path": {
                    "type": "string",
                    "description": "Relative path such as references/style-guide.md",
                },
            },
            "required": ["skill", "path"],
        },
    },
]

# Hostile inputs the library must reject, whatever the model (or a poisoned document) asks for
TRAVERSAL_ATTEMPTS = [
    ("release-notes", "assets/template.md"),
    ("release-notes", "../../../../.env"),
    ("release-notes", "/etc/passwd"),
    ("release-notes", "assets/../../sql-review/SKILL.md"),
    ("../release-notes", "SKILL.md"),
]


class SkillError(Exception):
    """Raised when a skill or a bundled file cannot be accessed."""


@dataclass(frozen=True)
class Skill:
    """Metadata of a discovered skill; the body stays on disk until it is loaded."""

    name: str
    description: str
    directory: Path


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md into its YAML front-matter and Markdown body."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        raise SkillError("missing YAML front-matter")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise SkillError("front-matter must be a YAML mapping")
    return meta, match.group(2).strip()


class SkillLibrary:
    """Discovers skills on disk and serves them one disclosure tier at a time."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.skills = self._discover()

    def _discover(self) -> dict[str, Skill]:
        """Read only the front-matter of each SKILL.md; a broken skill never breaks the agent."""
        skills: dict[str, Skill] = {}
        for skill_file in sorted(self.root.glob("*/SKILL.md")):
            try:
                meta, _ = split_front_matter(skill_file.read_text())
                name = str(meta.get("name", ""))
                description = str(meta.get("description", ""))
                if name != skill_file.parent.name or not SKILL_NAME_PATTERN.match(name):
                    raise SkillError(f"name {name!r} must match its folder and be kebab-case")
                if not description or len(description) > MAX_DESCRIPTION_CHARS:
                    raise SkillError(f"description must be 1-{MAX_DESCRIPTION_CHARS} characters")
                skills[name] = Skill(name, description, skill_file.parent)
            except (SkillError, yaml.YAMLError, OSError) as e:
                logger.error(f"Skipping {skill_file}: {e}")
        return skills

    def catalog(self) -> str:
        """Tier 1: one line per skill, cheap enough to keep in every request."""
        return "\n".join(f"- {s.name}: {s.description}" for s in self.skills.values())

    def load(self, name: str) -> str:
        """Tier 2: the SKILL.md body, plus an index of what tier 3 has to offer."""
        skill = self._get(name)
        _, body = split_front_matter((skill.directory / "SKILL.md").read_text())
        files = [
            path.relative_to(skill.directory).as_posix()
            for path in sorted(skill.directory.rglob("*"))
            if path.is_file() and path.name != "SKILL.md"
        ]
        listing = "\n".join(f"- {f}" for f in files) or "(none)"
        return f"{body}\n\nBundled files:\n{listing}"

    def read_file(self, name: str, relative_path: str) -> str:
        """Tier 3: a bundled file, confined to the skill's own folder."""
        root = self._get(name).directory.resolve()
        # resolve() collapses "../" and follows symlinks, so check the real location it lands on
        target = (root / relative_path).resolve()
        if not target.is_relative_to(root):
            raise SkillError(f"path {relative_path!r} escapes the skill folder")
        if not target.is_file():
            raise SkillError(f"no bundled file at {relative_path!r}")
        return target.read_text()

    def _get(self, name: str) -> Skill:
        """Look a skill up by catalog name, so a name can never be used as a path."""
        if name not in self.skills:
            raise SkillError(f"unknown skill {name!r}. Available: {', '.join(self.skills)}")
        return self.skills[name]

    def eager_size(self) -> int:
        """Characters the system prompt would carry if every skill were inlined up front."""
        return sum(
            len(path.read_text())
            for skill in self.skills.values()
            for path in skill.directory.rglob("*")
            if path.is_file()
        )


class SkillsAgent:
    """Agent loop whose capabilities come from a skill catalog instead of a long prompt."""

    def __init__(self, library: SkillLibrary) -> None:
        self.client = anthropic.Anthropic()
        self.library = library
        self.token_tracker = AnthropicTokenTracker()
        self.disclosures: list[str] = []
        # Frozen for the whole session: skills arrive as tool results, never as prompt edits,
        # which keeps the prompt cache valid and earlier thinking blocks replayable
        self.system_prompt = BASE_SYSTEM_PROMPT.format(catalog=library.catalog())

    def execute_tool(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Run a tool and return (content, is_error) so failures reach the model as data."""
        try:
            if name == "load_skill":
                content = self.library.load(tool_input["name"])
                self.disclosures.append(f"tier 2 · {tool_input['name']}")
            elif name == "read_skill_file":
                content = self.library.read_file(tool_input["skill"], tool_input["path"])
                self.disclosures.append(f"tier 3 · {tool_input['skill']}/{tool_input['path']}")
            else:
                return f"Unknown tool: {name}", True
            return content, False
        except (SkillError, KeyError, ValueError, OSError) as e:
            logger.warning(f"Rejected {name}: {e}")
            return f"Error: {e}", True

    def run(self, task: str) -> str:
        """Execute the agent loop for one task."""
        messages: list[Any] = [{"role": "user", "content": task}]

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"--- Iteration {iteration + 1} ---")
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                output_config={"effort": EFFORT},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=self.system_prompt,
                tools=TOOLS,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            # Append the full content: thinking blocks must be replayed unchanged
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                text = "\n".join(b.text for b in response.content if b.type == "text")
                return text or f"(no text returned, stop_reason={response.stop_reason})"

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"🔧 {block.name}({json.dumps(block.input)})")
                    content, is_error = self.execute_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                            "is_error": is_error,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

        return "Stopped: reached the iteration limit before finishing."


def build_disclosure_table(library: SkillLibrary) -> Table:
    """Compare the always-on cost of a catalog with inlining every skill."""
    catalog_chars = len(BASE_SYSTEM_PROMPT.format(catalog=library.catalog()))
    eager_chars = catalog_chars + library.eager_size()

    table = Table(title="System prompt size")
    table.add_column("Strategy")
    table.add_column("Characters", justify="right")
    table.add_column("≈ Tokens", justify="right")
    table.add_row("Progressive (catalog only)", f"{catalog_chars:,}", f"{catalog_chars // 4:,}")
    table.add_row("Eager (inline every skill)", f"{eager_chars:,}", f"{eager_chars // 4:,}")
    return table


def build_guard_table(library: SkillLibrary) -> Table:
    """Show what the path guard does with hostile inputs."""
    table = Table(title="Path traversal guard")
    table.add_column("Skill")
    table.add_column("Requested path")
    table.add_column("Outcome")
    for skill, path in TRAVERSAL_ATTEMPTS:
        try:
            library.read_file(skill, path)
            table.add_row(skill, path, "[green]allowed[/green]")
        except SkillError as e:
            table.add_row(skill, path, f"[red]blocked[/red]: {escape(str(e))}")
    return table


def main() -> None:
    """Main orchestration function."""
    console = Console()
    library = SkillLibrary(SKILLS_DIR)

    catalog = "\n".join(f"  - {line[2:]}" for line in library.catalog().splitlines())
    console.print(Panel(catalog, title="Discovered skills"))
    console.print(build_disclosure_table(library))
    console.print(build_guard_table(library))

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("\n[yellow]Set ANTHROPIC_API_KEY to run the live agent.[/yellow]")
        return

    tasks = [
        "Write release notes for v2.4.0. Changes: added CSV export to reports; fixed a crash "
        "when a project has no members; the /v1/search endpoint now requires an API key; "
        "upgraded the database driver.",
        "Review this query: SELECT * FROM orders WHERE YEAR(created_at) = 2025 "
        "AND customer_id IN (SELECT id FROM customers WHERE status = 'active')",
        "What is the capital of Australia?",
    ]
    examples = "\n".join(f"  {i}. {task[:80]}..." for i, task in enumerate(tasks, 1))
    console.print(
        Panel(
            f"Pick an example or type your own task:\n{examples}\n\nType 'quit' to exit.",
            title="Skills Agent (Anthropic)",
        )
    )

    agent = SkillsAgent(library)
    try:
        while True:
            console.print("\n[bold green]You:[/bold green] ", end="")
            user_input = input().strip()
            if user_input.lower() in ("exit", "quit", "q", ""):
                break
            if user_input.isdigit() and 1 <= int(user_input) <= len(tasks):
                user_input = tasks[int(user_input) - 1]

            agent.disclosures.clear()
            answer = agent.run(user_input)
            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(answer))
            loaded = "\n".join(agent.disclosures) or "nothing beyond the catalog"
            console.print(Panel(loaded, title="What this task loaded"))
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Interrupted.[/yellow]")
    except anthropic.APIError as e:
        logger.error(f"API error: {e}")

    agent.token_tracker.report()


if __name__ == "__main__":
    main()
