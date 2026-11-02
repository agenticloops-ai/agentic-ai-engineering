"""Layer: skills. Expertise loaded on demand from folders, one disclosure tier at a time."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from common import setup_logging
from extensible_agent.tools import Tool, ToolOutput

logger = setup_logging(__name__)


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
        raise ValueError("missing YAML front-matter")
    return yaml.safe_load(match.group(1)), match.group(2).strip()


class SkillLayer:
    """Discovers skills and exposes them as a catalog plus two tools."""

    def __init__(self, root: Path) -> None:
        self.skills: dict[str, Skill] = {}
        for path in sorted(root.glob("*/SKILL.md")):
            try:
                meta, _ = split_front_matter(path.read_text())
                self.skills[meta["name"]] = Skill(meta["name"], meta["description"], path.parent)
            except (ValueError, KeyError, yaml.YAMLError) as e:
                logger.error(f"Skipping {path}: {e}")

    def catalog(self) -> str:
        """Tier 1: one line per skill, for the system prompt."""
        return "\n".join(f"- {s.name}: {s.description}" for s in self.skills.values())

    def _get(self, name: str) -> Skill:
        if name not in self.skills:
            raise ValueError(f"unknown skill {name!r}")
        return self.skills[name]

    async def _load_skill(self, tool_input: dict[str, Any]) -> ToolOutput:
        """Tier 2: the SKILL.md body, plus an index of its bundled files."""
        skill = self._get(tool_input["name"])
        _, body = split_front_matter((skill.directory / "SKILL.md").read_text())
        files = [
            p.relative_to(skill.directory).as_posix()
            for p in sorted(skill.directory.rglob("*"))
            if p.is_file() and p.name != "SKILL.md"
        ]
        return f"{body}\n\nBundled files: {', '.join(files) or '(none)'}", False

    async def _read_skill_file(self, tool_input: dict[str, Any]) -> ToolOutput:
        """Tier 3: a bundled file, confined to the skill's own folder."""
        root = self._get(tool_input["skill"]).directory.resolve()
        target = (root / tool_input["path"]).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return f"No bundled file at {tool_input['path']!r}", True
        return target.read_text(), False

    def tools(self) -> list[Tool]:
        """Expose tiers 2 and 3 to the agent."""
        return [
            Tool(
                "load_skill",
                "Load the full instructions of a skill from the catalog.",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                self._load_skill,
            ),
            Tool(
                "read_skill_file",
                "Read a file bundled with a skill, by path relative to its folder.",
                {
                    "type": "object",
                    "properties": {"skill": {"type": "string"}, "path": {"type": "string"}},
                    "required": ["skill", "path"],
                },
                self._read_skill_file,
            ),
        ]
