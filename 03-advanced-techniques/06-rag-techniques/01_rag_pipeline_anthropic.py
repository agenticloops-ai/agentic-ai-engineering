"""
RAG Pipeline (Anthropic)

Demonstrates a complete Retrieval-Augmented Generation pipeline: ingest
documents, chunk, embed with a local sentence-transformer model, index in
ChromaDB + BM25, retrieve with hybrid search and reranking, then generate
answers with Claude.

Requires ANTHROPIC_API_KEY environment variable.
"""

import logging
import os
from pathlib import Path

# Suppress noisy third-party logs and progress bars before they initialize
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["SAFETENSORS_LOG_LEVEL"] = "error"
for _lib in (
    "sentence_transformers", "transformers", "torch", "huggingface_hub",
    "chromadb", "bm25s", "safetensors",
):
    logging.getLogger(_lib).setLevel(logging.ERROR)

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, setup_logging
from common.menu import interactive_menu
from rag import HybridRetriever, LocalEmbedder, Reranker, VectorStore, recursive_split

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

# Model configuration
MODEL = "claude-sonnet-4-5-20250929"
SAMPLE_DOCS_DIR = Path(__file__).parent / "sample_docs"
CHROMA_PERSIST_DIR = str(Path(__file__).parent / ".chroma_db")

SYSTEM_PROMPT = (
    "You are a technical support assistant for TechFlow Solutions. "
    "Answer questions using ONLY the provided context. "
    "Cite the source document for each fact (e.g., [api_reference.md]). "
    "If the context doesn't contain the answer, say so clearly — do not make things up."
)

# Pre-defined demo questions covering different documents and retrieval modes
DEMO_QUESTIONS = [
    "How do I authenticate with the TechFlow API?",
    "What database does TechFlow use for caching?",
    "How do I roll back a failed deployment?",
    "Why are my webhooks not firing?",
    "What is the rate limit for the Pro plan?",
    "Explain how services communicate with each other in the TechFlow architecture.",
]


class RAGPipeline:
    """Full RAG pipeline: ingest → retrieve → generate."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker

        # Build the retrieval stack
        self.embedder = LocalEmbedder()
        self.store = VectorStore(self.embedder, persist_dir=CHROMA_PERSIST_DIR)
        self.reranker = Reranker()
        self.retriever = HybridRetriever(self.store, self.reranker)

    def ingest(self, docs_dir: Path) -> int:
        """Load markdown files, chunk, embed, and index. Return chunk count."""
        all_chunks = []

        for doc_path in sorted(docs_dir.glob("*.md")):
            text = doc_path.read_text(encoding="utf-8")
            chunks = recursive_split(text, source=doc_path.name)
            all_chunks.extend(chunks)
            logger.info("Chunked %s → %d chunks", doc_path.name, len(chunks))

        self.store.add_chunks(all_chunks)
        return len(all_chunks)

    def query(self, question: str, top_k: int = 5) -> tuple[str, list]:
        """Retrieve relevant chunks and generate an answer with citations."""
        chunks = self.retriever.retrieve(question, top_k=top_k)
        context = self._build_context(chunks)
        answer = self._generate(question, context)
        return answer, chunks

    def _build_context(self, chunks: list) -> str:
        """Format retrieved chunks as numbered context blocks."""
        if not chunks:
            return "No relevant context found."

        blocks = []
        for i, chunk in enumerate(chunks, 1):
            blocks.append(f"[{i}] Source: {chunk.source}\n{chunk.content}")
        return "\n\n---\n\n".join(blocks)

    def _generate(self, question: str, context: str) -> str:
        """Send question + context to Claude, return answer."""
        user_message = f"Context:\n{context}\n\nQuestion: {question}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        self.token_tracker.track(response.usage)
        return str(response.content[0].text)


def _render_chunks(console: Console, chunks: list) -> None:
    """Display retrieved chunks with source and preview."""
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#", style="dim", width=3)
    table.add_column("Source", style="cyan", min_width=20)
    table.add_column("Preview", ratio=1)

    for i, chunk in enumerate(chunks, 1):
        preview = chunk.content[:120].replace("\n", " ") + "..."
        table.add_row(str(i), chunk.source, f"[dim]{preview}[/dim]")

    console.print(Panel(table, title="Retrieved Chunks", border_style="dim", padding=(0, 1)))


def _run_demo(console: Console, pipeline: RAGPipeline) -> None:
    """Run pre-defined demo questions one at a time, waiting for user input."""
    console.print(f"\n[bold]Running {len(DEMO_QUESTIONS)} demo questions.[/bold]")
    console.print("[dim]Press Enter to run each question, or 'q' to stop.[/dim]\n")

    for i, question in enumerate(DEMO_QUESTIONS, 1):
        console.print(f"[bold green]Question {i}/{len(DEMO_QUESTIONS)}:[/bold green] {question}")
        console.print("[dim]Press Enter to run...[/dim] ", end="")
        try:
            if input().strip().lower() == "q":
                break
        except EOFError:
            break

        try:
            answer, chunks = pipeline.query(question)

            _render_chunks(console, chunks)

            console.print("\n[bold blue]Answer:[/bold blue]")
            console.print(Markdown(answer))
            console.print("\n" + "─" * 60 + "\n")

        except Exception as e:
            logger.error("Error processing question %d: %s", i, e)
            console.print(f"[red]Error: {e}[/red]\n")


def _run_interactive(console: Console, pipeline: RAGPipeline) -> None:
    """Interactive mode — user asks questions."""
    console.print(
        "\n[bold]Interactive mode[/bold] — ask questions about TechFlow.\n"
        "Type [bold]'quit'[/bold] or [bold]'exit'[/bold] to end.\n"
    )

    while True:
        console.print("[bold green]Question:[/bold green] ", end="")
        user_input = input().strip()

        if user_input.lower() in ["quit", "exit", ""]:
            break

        try:
            answer, chunks = pipeline.query(user_input)

            _render_chunks(console, chunks)

            console.print("\n[bold blue]Answer:[/bold blue]")
            console.print(Markdown(answer))
            console.print()

        except Exception as e:
            logger.error("Error processing question: %s", e)
            console.print(f"\n[red]Error: {e}[/red]")


def main() -> None:
    """Main orchestration function for the RAG pipeline demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()

    with console.status("[bold]Loading embedding model (first run downloads ~80MB)...[/bold]"):
        pipeline = RAGPipeline(MODEL, token_tracker)

    header = Panel(
        "[bold cyan]RAG Pipeline Demo[/bold cyan]\n\n"
        "This demo ingests TechFlow documentation, builds a hybrid index\n"
        "(vector + BM25), and answers questions with source citations.\n\n"
        "[bold]Pipeline:[/bold] Chunk → Embed (local) → Index (ChromaDB + BM25)\n"
        "         → Hybrid Retrieve → Rerank (FlashRank) → Generate (Claude)\n\n"
        "[bold]Try these sample questions:[/bold]\n"
        "  1. How do I authenticate with the TechFlow API?\n"
        "  2. What database does TechFlow use for caching?\n"
        "  3. How do I roll back a failed deployment?\n"
        "  4. Why are my webhooks not firing?\n"
        "  5. What is the rate limit for the Pro plan?",
        title="RAG Pipeline",
    )
    console.print(header)

    # Ingest documents
    console.print("\n[bold]Ingesting documents...[/bold]")
    try:
        chunk_count = pipeline.ingest(SAMPLE_DOCS_DIR)
        console.print(
            f"[green]Indexed {chunk_count} chunks from "
            f"{len(list(SAMPLE_DOCS_DIR.glob('*.md')))} documents[/green]\n"
        )
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        console.print(f"[red]Ingestion failed: {e}[/red]")
        return

    mode = interactive_menu(
        console,
        items=[
            "Demo — run sample questions with full pipeline",
            "Interactive — ask your own questions",
        ],
        title="Select Mode",
    )

    if mode is None:
        return

    if mode.startswith("Demo"):
        _run_demo(console, pipeline)
    else:
        _run_interactive(console, pipeline)

    # Final token report
    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
