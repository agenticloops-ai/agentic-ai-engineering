"""Local sentence-transformer embeddings — no API key required."""

import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Small, fast, and good quality — downloads ~80MB on first run
DEFAULT_MODEL = "all-MiniLM-L6-v2"


class LocalEmbedder:
    """Generates embeddings using a local sentence-transformers model."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        logger.info("Loading embedding model: %s", model_name)
        self.model = SentenceTransformer(model_name)
        logger.info(
            "Embedding model loaded (dimension=%d)", self.model.get_sentence_embedding_dimension()
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents for indexing."""
        if not texts:
            return []

        embeddings = self.model.encode(texts, show_progress_bar=False)
        logger.info("Embedded %d documents", len(texts))
        return [e.tolist() for e in embeddings]

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query."""
        embedding = self.model.encode(query)
        result: list[float] = embedding.tolist()
        return result
