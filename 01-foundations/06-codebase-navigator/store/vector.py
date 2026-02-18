"""
Vector Store

ChromaDB-based vector store for semantic search over indexed codebases.
This is the "Retrieval" augmentation of the Augmented LLM pattern.
"""

from pathlib import Path
from typing import Any

import chromadb

from common.logging_config import setup_logging

logger = setup_logging(__name__)

# Persist ChromaDB data to local directory
DEFAULT_CHROMA_PATH = str(Path(__file__).parent.parent / "data" / "chroma")


class VectorStore:
    """ChromaDB wrapper for storing and querying code embeddings."""

    def __init__(self, persist_dir: str = DEFAULT_CHROMA_PATH) -> None:
        self.client = chromadb.PersistentClient(path=persist_dir)
        logger.info("ChromaDB initialized at %s", persist_dir)

    def get_or_create_collection(self, name: str) -> chromadb.Collection:
        """Get or create a collection for a repository."""
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Add code chunks with pre-computed embeddings to a collection."""
        collection = self.get_or_create_collection(collection_name)
        # ChromaDB has a batch size limit, add in chunks of 500
        batch_size = 500
        for i in range(0, len(ids), batch_size):
            end = i + batch_size
            collection.add(
                ids=ids[i:end],
                documents=documents[i:end],
                embeddings=embeddings[i:end],
                metadatas=metadatas[i:end],
            )
        logger.info("Added %d chunks to collection '%s'", len(ids), collection_name)

    def search(
        self,
        query_embedding: list[float],
        collection_name: str | None = None,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for similar code chunks across one or all collections."""
        collections = (
            [self.client.get_collection(collection_name)]
            if collection_name
            else self.client.list_collections()
        )

        all_results: list[dict[str, Any]] = []
        for collection in collections:
            if collection.count() == 0:
                continue
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            for j in range(len(results["ids"][0])):
                all_results.append(
                    {
                        "id": results["ids"][0][j],
                        "content": results["documents"][0][j],
                        "metadata": results["metadatas"][0][j],
                        "distance": results["distances"][0][j],
                        "collection": collection.name,
                    }
                )

        # Sort by distance (lower = more similar for cosine)
        all_results.sort(key=lambda x: x["distance"])
        return all_results[:n_results]

    def list_collections(self) -> list[dict[str, Any]]:
        """List all indexed repositories with stats."""
        result = []
        for collection in self.client.list_collections():
            result.append(
                {
                    "name": collection.name,
                    "chunks": collection.count(),
                }
            )
        return result

    def collection_exists(self, name: str) -> bool:
        """Check if a collection already exists."""
        return any(c.name == name for c in self.client.list_collections())
