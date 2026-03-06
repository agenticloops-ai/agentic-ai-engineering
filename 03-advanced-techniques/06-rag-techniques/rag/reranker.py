"""FlashRank reranker — lightweight, CPU-only, no API key needed."""

import logging

from rag.chunker import Chunk

logger = logging.getLogger(__name__)


class Reranker:
    """Reranks chunks by relevance to a query using FlashRank.

    FlashRank uses a small ONNX model (~4MB) that runs on CPU.
    No API key or GPU required — ideal for tutorials and prototyping.
    """

    def __init__(self, model: str = "ms-marco-MiniLM-L-12-v2"):
        from flashrank import Ranker

        self.ranker = Ranker(model_name=model)
        logger.info("Reranker initialized with model=%s", model)

    def rerank(self, query: str, chunks: list[Chunk], top_k: int = 5) -> list[Chunk]:
        """Rerank chunks by relevance to query, return top_k."""
        if not chunks:
            return []

        from flashrank import RerankRequest

        passages = [{"id": c.id, "text": c.content, "meta": {"source": c.source}} for c in chunks]
        request = RerankRequest(query=query, passages=passages)
        results = self.ranker.rerank(request)

        # Map back to Chunk objects, sorted by reranker score (descending)
        chunk_lookup = {c.id: c for c in chunks}
        reranked = []
        for r in sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]:
            chunk = chunk_lookup.get(r["id"])
            if chunk:
                reranked.append(chunk)

        logger.info("Reranked %d chunks → top %d", len(chunks), len(reranked))
        return reranked
