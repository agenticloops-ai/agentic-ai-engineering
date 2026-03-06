"""Working memory — in-session buffer with importance-based eviction."""

from common.logging_config import setup_logging

from .models import MemoryEntry, MemoryType

logger = setup_logging(__name__)


class WorkingMemory:
    """Session-scoped buffer that evicts lowest-importance entries when full."""

    def __init__(self, max_items: int = 50) -> None:
        self.max_items = max_items
        self._entries: list[MemoryEntry] = []

    def add(
        self,
        content: str,
        importance: float = 0.5,
        metadata: dict | None = None,
    ) -> MemoryEntry:
        """Add a memory, evicting the least important entry if at capacity."""
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.WORKING,
            importance=importance,
            metadata=metadata or {},
        )

        if len(self._entries) >= self.max_items:
            # Evict lowest importance
            self._entries.sort(key=lambda e: e.importance)
            evicted = self._entries.pop(0)
            logger.info("Evicted working memory: %s", evicted.content[:60])

        self._entries.append(entry)
        return entry

    def get_recent(self, n: int = 10) -> list[MemoryEntry]:
        """Return the N most recent entries."""
        return sorted(self._entries, key=lambda e: e.timestamp, reverse=True)[:n]

    def get_important(self, threshold: float = 0.7) -> list[MemoryEntry]:
        """Return entries above the importance threshold."""
        return [e for e in self._entries if e.importance >= threshold]

    def get_all(self) -> list[MemoryEntry]:
        """Return all entries ordered by timestamp."""
        return sorted(self._entries, key=lambda e: e.timestamp)

    def clear(self) -> None:
        """Clear all working memory."""
        count = len(self._entries)
        self._entries.clear()
        logger.info("Cleared %d working memory entries", count)

    def stats(self) -> dict:
        """Return working memory statistics."""
        return {
            "count": len(self._entries),
            "max_items": self.max_items,
            "avg_importance": (
                sum(e.importance for e in self._entries) / len(self._entries)
                if self._entries
                else 0.0
            ),
        }
