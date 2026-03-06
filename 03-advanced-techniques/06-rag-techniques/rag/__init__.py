"""RAG pipeline components: chunking, embedding, storage, retrieval, and reranking."""

import logging
import os

# Suppress noisy third-party logs and progress bars before they initialize
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["SAFETENSORS_LOG_LEVEL"] = "error"
for _lib in (
    "sentence_transformers",
    "transformers",
    "torch",
    "huggingface_hub",
    "chromadb",
    "bm25s",
    "safetensors",
):
    logging.getLogger(_lib).setLevel(logging.ERROR)

from rag.chunker import Chunk, recursive_split  # noqa: E402
from rag.embedder import LocalEmbedder  # noqa: E402
from rag.reranker import Reranker  # noqa: E402
from rag.retriever import HybridRetriever  # noqa: E402
from rag.store import VectorStore  # noqa: E402

__all__ = [
    "Chunk",
    "HybridRetriever",
    "Reranker",
    "VectorStore",
    "LocalEmbedder",
    "recursive_split",
]
