"""Hybrid retriever combining vector search, BM25, and reranking."""

import logging

from rag.chunker import Chunk
from rag.reranker import Reranker
from rag.store import VectorStore

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Combines vector search and BM25 with reciprocal rank fusion and reranking."""

    def __init__(self, store: VectorStore, reranker: Reranker | None = None):
        self.store = store
        self.reranker = reranker

    def retrieve(self, query: str, top_k: int = 5, candidates: int = 20) -> list[Chunk]:
        """Full retrieval pipeline: vector + BM25 → RRF → rerank → top_k.

        Retrieves `candidates` from each method, fuses with RRF,
        then optionally reranks to produce the final top_k results.
        """
        vector_results = self.store.vector_search(query, top_k=candidates)
        keyword_results = self.store.keyword_search(query, top_k=candidates)

        logger.info(
            "Retrieved %d vector + %d keyword results for: %s",
            len(vector_results),
            len(keyword_results),
            query[:60],
        )

        # Fuse results with reciprocal rank fusion
        fused = self._reciprocal_rank_fusion(vector_results, keyword_results)
        fused_chunks = [chunk for chunk, _ in fused]

        # Rerank if available
        if self.reranker and fused_chunks:
            return self.reranker.rerank(query, fused_chunks, top_k=top_k)

        return fused_chunks[:top_k]

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[tuple[Chunk, float]],
        keyword_results: list[tuple[Chunk, float]],
        k: int = 60,
    ) -> list[tuple[Chunk, float]]:
        """Merge ranked lists using Reciprocal Rank Fusion.

        RRF score = sum(1 / (k + rank)) across all lists where the item appears.
        k=60 is the standard constant from the original paper.
        """
        scores: dict[str, float] = {}
        chunk_map: dict[str, Chunk] = {}

        for rank, (chunk, _) in enumerate(vector_results):
            scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (k + rank + 1)
            chunk_map[chunk.id] = chunk

        for rank, (chunk, _) in enumerate(keyword_results):
            scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (k + rank + 1)
            chunk_map[chunk.id] = chunk

        # Sort by fused score descending
        sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        return [(chunk_map[cid], scores[cid]) for cid in sorted_ids]
