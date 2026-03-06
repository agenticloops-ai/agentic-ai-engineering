"""Semantic memory — facts and knowledge stored in ChromaDB vector database."""

import chromadb
from common.logging_config import setup_logging

from .models import MemoryEntry, MemoryType

logger = setup_logging(__name__)


class SemanticMemory:
    """Long-term factual memory backed by ChromaDB with cosine similarity search."""

    def __init__(self, persist_dir: str = "data/chroma") -> None:
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="semantic_memory",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB initialized at %s (%d entries)", persist_dir, self.collection.count())

    def save(self, entry: MemoryEntry) -> None:
        """Save a memory — ChromaDB handles embedding automatically."""
        entry.memory_type = MemoryType.SEMANTIC
        self.collection.add(
            ids=[entry.id],
            documents=[entry.content],
            metadatas=[
                {
                    "timestamp": entry.timestamp.isoformat(),
                    "importance": entry.importance,
                    **{k: str(v) for k, v in entry.metadata.items()},
                }
            ],
        )
        logger.info("Saved semantic memory: %s", entry.content[:60])

    def search(self, query: str, limit: int = 5) -> list[tuple[MemoryEntry, float]]:
        """Search by semantic similarity — returns (entry, similarity_score) pairs."""
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(limit, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        entries: list[tuple[MemoryEntry, float]] = []
        for i in range(len(results["ids"][0])):
            metadata = results["metadatas"][0][i]
            # Cosine distance → similarity: similarity = 1 - distance
            similarity = 1.0 - results["distances"][0][i]
            entry = MemoryEntry(
                id=results["ids"][0][i],
                content=results["documents"][0][i],
                memory_type=MemoryType.SEMANTIC,
                importance=float(metadata.get("importance", 0.5)),
                metadata={
                    k: v for k, v in metadata.items() if k not in ("timestamp", "importance")
                },
            )
            entries.append((entry, similarity))

        return entries

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        try:
            self.collection.delete(ids=[memory_id])
            logger.info("Deleted semantic memory: %s", memory_id)
            return True
        except Exception as e:
            logger.error("Failed to delete semantic memory %s: %s", memory_id, e)
            return False

    def list_all(self) -> list[MemoryEntry]:
        """Return all semantic memories."""
        if self.collection.count() == 0:
            return []

        results = self.collection.get(include=["documents", "metadatas"])
        entries: list[MemoryEntry] = []
        for i in range(len(results["ids"])):
            metadata = results["metadatas"][i]
            entry = MemoryEntry(
                id=results["ids"][i],
                content=results["documents"][i],
                memory_type=MemoryType.SEMANTIC,
                importance=float(metadata.get("importance", 0.5)),
                metadata={
                    k: v for k, v in metadata.items() if k not in ("timestamp", "importance")
                },
            )
            entries.append(entry)
        return entries

    def clear(self) -> None:
        """Clear all semantic memories by recreating the collection."""
        self.client.delete_collection("semantic_memory")
        self.collection = self.client.get_or_create_collection(
            name="semantic_memory",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Cleared all semantic memories")

    def stats(self) -> dict:
        """Return semantic memory statistics."""
        return {
            "count": self.collection.count(),
            "collection": self.collection.name,
        }
