"""ChromaDB vector store with BM25 keyword index."""

import logging

import bm25s
import chromadb

from rag.chunker import Chunk
from rag.embedder import LocalEmbedder

logger = logging.getLogger(__name__)


class VectorStore:
    """Dual-index store: ChromaDB for vector search, BM25 for keyword search."""

    def __init__(self, embedder: LocalEmbedder, persist_dir: str | None = None):
        self.embedder = embedder
        self.chunks: list[Chunk] = []
        self._chunk_lookup: dict[str, Chunk] = {}

        # ChromaDB — persistent or in-memory
        if persist_dir:
            self.chroma_client = chromadb.PersistentClient(path=persist_dir)
        else:
            self.chroma_client = chromadb.Client()

        self.collection = self.chroma_client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

        # BM25 — built after ingestion
        self.bm25: bm25s.BM25 | None = None

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """Embed and index chunks in both vector store and BM25."""
        if not chunks:
            return

        self.chunks = chunks
        self._chunk_lookup = {c.id: c for c in chunks}

        texts = [c.content for c in chunks]
        ids = [c.id for c in chunks]
        metadatas = [{"source": c.source, "chunk_index": c.chunk_index} for c in chunks]

        # Embed and add to ChromaDB
        embeddings = self.embedder.embed_documents(texts)
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("Indexed %d chunks in ChromaDB", len(chunks))

        # Build BM25 index
        tokenized = bm25s.tokenize(texts, stopwords="en", show_progress=False)
        self.bm25 = bm25s.BM25()
        self.bm25.index(tokenized, show_progress=False)
        logger.info("Built BM25 index over %d chunks", len(chunks))

    def vector_search(self, query: str, top_k: int = 20) -> list[tuple[Chunk, float]]:
        """Dense vector similarity search via ChromaDB."""
        query_embedding = self.embedder.embed_query(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, len(self.chunks)),
        )

        scored: list[tuple[Chunk, float]] = []
        if results["ids"] and results["ids"][0]:
            for chunk_id, distance in zip(results["ids"][0], results["distances"][0]):
                chunk = self._chunk_lookup.get(chunk_id)
                if chunk:
                    # ChromaDB returns cosine distance; convert to similarity
                    similarity = 1.0 - distance
                    scored.append((chunk, similarity))

        return scored

    def keyword_search(self, query: str, top_k: int = 20) -> list[tuple[Chunk, float]]:
        """BM25 keyword search."""
        if self.bm25 is None or not self.chunks:
            return []

        tokenized_query = bm25s.tokenize(query, stopwords="en")
        results, scores = self.bm25.retrieve(tokenized_query, k=min(top_k, len(self.chunks)))

        scored: list[tuple[Chunk, float]] = []
        for idx, score in zip(results[0], scores[0]):
            if 0 <= idx < len(self.chunks) and score > 0:
                scored.append((self.chunks[idx], float(score)))

        return scored

    @property
    def chunk_count(self) -> int:
        """Number of indexed chunks."""
        return len(self.chunks)
