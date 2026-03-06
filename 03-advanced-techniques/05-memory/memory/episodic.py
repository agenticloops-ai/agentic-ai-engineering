"""Episodic memory — timestamped events persisted to a JSON file."""

import json
from pathlib import Path

from common.logging_config import setup_logging

from .models import MemoryEntry, MemoryType

logger = setup_logging(__name__)


class EpisodicMemory:
    """Long-term event memory backed by a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("data/episodic.json")
        self._entries: list[MemoryEntry] = []
        self._load()

    def _load(self) -> None:
        """Load memories from disk."""
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._entries = [MemoryEntry.from_dict(d) for d in raw]
                logger.info("Loaded %d episodic memories from %s", len(self._entries), self.path)
            except (json.JSONDecodeError, KeyError) as e:
                logger.error("Failed to load episodic memory: %s", e)
                self._entries = []
        else:
            logger.info("No existing episodic memory at %s", self.path)

    def _save(self) -> None:
        """Persist memories to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [e.to_dict() for e in self._entries]
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save(self, entry: MemoryEntry) -> None:
        """Save a memory entry to the episodic store."""
        entry.memory_type = MemoryType.EPISODIC
        self._entries.append(entry)
        self._save()
        logger.info("Saved episodic memory: %s", entry.content[:60])

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search memories by keyword matching."""
        query_lower = query.lower()
        query_words = query_lower.split()

        scored: list[tuple[MemoryEntry, int]] = []
        for entry in self._entries:
            content_lower = entry.content.lower()
            # Score by number of query words found
            score = sum(1 for word in query_words if word in content_lower)
            if score > 0:
                scored.append((entry, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, _ in scored[:limit]]

    def get_recent(self, n: int = 10) -> list[MemoryEntry]:
        """Return the N most recent episodic memories."""
        return sorted(self._entries, key=lambda e: e.timestamp, reverse=True)[:n]

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        for i, entry in enumerate(self._entries):
            if entry.id == memory_id:
                self._entries.pop(i)
                self._save()
                logger.info("Deleted episodic memory: %s", memory_id)
                return True
        return False

    def list_all(self) -> list[MemoryEntry]:
        """Return all episodic memories ordered by timestamp."""
        return sorted(self._entries, key=lambda e: e.timestamp)

    def clear(self) -> None:
        """Clear all episodic memories."""
        count = len(self._entries)
        self._entries.clear()
        self._save()
        logger.info("Cleared %d episodic memories", count)

    def stats(self) -> dict:
        """Return episodic memory statistics."""
        return {
            "count": len(self._entries),
            "file": str(self.path),
            "oldest": self._entries[0].timestamp.isoformat() if self._entries else None,
            "newest": self._entries[-1].timestamp.isoformat() if self._entries else None,
        }
