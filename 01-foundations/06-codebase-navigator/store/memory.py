"""
Memory Store

Persistent JSON-based memory for storing facts, insights, and preferences across sessions.
This is the "Memory" augmentation of the Augmented LLM pattern.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.logging_config import setup_logging

logger = setup_logging(__name__)

# Default memory file location
DEFAULT_MEMORY_PATH = Path(__file__).parent.parent / "memory.json"


class MemoryStore:
    """Persistent memory store backed by a JSON file."""

    def __init__(self, path: Path = DEFAULT_MEMORY_PATH) -> None:
        self.path = path
        self.data: dict[str, list[dict[str, Any]]] = {
            "facts": [],
            "insights": [],
            "preferences": [],
        }
        self._load()

    def _load(self) -> None:
        """Load memories from disk."""
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
                total = sum(len(v) for v in self.data.values())
                logger.info("Loaded %d memories from %s", total, self.path)
            except (json.JSONDecodeError, KeyError) as e:
                logger.error("Failed to load memory file: %s", e)
                self.data = {"facts": [], "insights": [], "preferences": []}

    def _save(self) -> None:
        """Persist memories to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def save(self, category: str, content: str, repos: list[str] | None = None) -> str:
        """Save a memory entry."""
        if category not in self.data:
            return f"Invalid category: {category}. Use: fact, insight, preference"

        entry: dict[str, Any] = {
            "content": content,
            "created": datetime.now(timezone.utc).isoformat(),
        }
        if repos:
            entry["repos"] = repos

        self.data[category].append(entry)
        self._save()
        logger.info("Saved %s: %s", category, content[:80])
        return f"Saved {category}: {content}"

    def recall(self, query: str | None = None) -> dict[str, list[dict[str, Any]]]:
        """Recall memories, optionally filtered by keyword."""
        if not query:
            return self.data

        query_lower = query.lower()
        filtered: dict[str, list[dict[str, Any]]] = {}
        for category, entries in self.data.items():
            matches = [e for e in entries if query_lower in e["content"].lower()]
            if matches:
                filtered[category] = matches
        return filtered

    def summary(self) -> str:
        """Return a brief summary for inclusion in system prompts."""
        parts = []
        for category, entries in self.data.items():
            if entries:
                parts.append(
                    f"{category} ({len(entries)}): " + "; ".join(e["content"] for e in entries[-3:])
                )
        return "\n".join(parts) if parts else "No memories stored yet."
