"""
Agentic RAG (Anthropic)

Demonstrates RAG as a tool within an agent loop. The agent decides *when* to
search, *what query* to formulate, and *whether results are sufficient*. If
initial retrieval is inadequate, the agent reformulates and searches again.

Contrast with Script 01 (pipeline RAG) where every question triggers retrieval.
Here the agent exercises judgment — some questions can be answered from
conversation context, and the agent chooses its own search queries.

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

from common import AnthropicTokenTracker, setup_logging
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
    "You are a technical support agent for TechFlow Solutions with access to "
    "the company's documentation through a search tool.\n\n"
    "Guidelines:\n"
    "- Search the documentation when you need specific technical details\n"
    "- Use targeted, specific search queries rather than broad ones\n"
    "- If initial results are insufficient, reformulate your query and search again\n"
    "- You don't need to search for every question — use your judgment\n"
    "- Always cite which document your information comes from (e.g., [api_reference.md])\n"
    "- If the documentation doesn't cover a topic, say so clearly"
)

TOOLS = [
    {
        "name": "search_docs",
        "description": (
            "Search the TechFlow documentation for information. "
            "Use specific, targeted queries for best results. "
            "You can call this multiple times with different queries to find more information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query — be specific and use technical terms",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    }
]


class AgenticRAG:
    """Agent that uses retrieval as a tool in its reasoning loop."""

    def __init__(
        self,
        model: str,
        retriever: HybridRetriever,
        token_tracker: AnthropicTokenTracker,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.retriever = retriever
        self.token_tracker = token_tracker
        self.messages: list[dict] = []

    def chat(self, user_input: str, console: Console) -> str:
        """Agent loop: send → detect tool calls → execute search → continue."""
        self.messages.append({"role": "user", "content": user_input})

        # Agent loop — continues until the model produces a text response
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages,
            )

            self.token_tracker.track(response.usage)

            # Check if the model wants to use tools
            if response.stop_reason == "tool_use":
                # Process all tool calls in this response
                self.messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        query = block.input.get("query", "")
                        top_k = min(block.input.get("top_k", 5), 10)

                        console.print(f"  [dim]Searching:[/dim] [italic]{query}[/italic]")

                        result = self._execute_search(query, top_k)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                self.messages.append({"role": "user", "content": tool_results})
                continue

            # Model produced a final text response
            assistant_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    assistant_text += block.text

            self.messages.append({"role": "assistant", "content": assistant_text})
            return assistant_text

    def _execute_search(self, query: str, top_k: int) -> str:
        """Run retrieval and format results for the agent."""
        chunks = self.retriever.retrieve(query, top_k=top_k)

        if not chunks:
            return "No relevant documents found for this query."

        results = []
        for i, chunk in enumerate(chunks, 1):
            results.append(f"[{i}] Source: {chunk.source}\n{chunk.content}")

        return "\n\n---\n\n".join(results)


def _build_retriever() -> HybridRetriever:
    """Build the retrieval stack and ingest documents."""
    embedder = LocalEmbedder()
    store = VectorStore(embedder, persist_dir=CHROMA_PERSIST_DIR)
    reranker = Reranker()
    retriever = HybridRetriever(store, reranker)

    # Ingest sample docs
    all_chunks = []
    for doc_path in sorted(SAMPLE_DOCS_DIR.glob("*.md")):
        text = doc_path.read_text(encoding="utf-8")
        chunks = recursive_split(text, source=doc_path.name)
        all_chunks.extend(chunks)

    store.add_chunks(all_chunks)
    return retriever


def main() -> None:
    """Main orchestration function for the agentic RAG demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()

    console.print(
        Panel(
            "[bold cyan]Agentic RAG Demo[/bold cyan]\n\n"
            "Unlike pipeline RAG (Script 01), this agent decides [bold]when[/bold] to search,\n"
            "[bold]what query[/bold] to use, and [bold]whether results are sufficient[/bold].\n\n"
            "The agent has a [cyan]search_docs[/cyan] tool it can call — or choose not to.\n"
            "Watch for:\n"
            "  - Agent choosing its own search queries (may differ from your question)\n"
            "  - Agent searching multiple times for complex questions\n"
            "  - Agent answering from conversation context without searching\n\n"
            "[bold]Try these questions:[/bold]\n"
            "  1. How do I authenticate with the API?\n"
            "  2. What happens when a deployment fails? (follow up: what about database rollbacks?)\n"
            "  3. Why might my API requests be slow?\n"
            "  4. Compare the different plan tiers.\n\n"
            "Type [bold]'quit'[/bold] or [bold]'exit'[/bold] to end.",
            title="Agentic RAG",
        )
    )

    # Build retrieval stack (first run downloads embedding model ~80MB)
    console.print("\n[bold]Loading models and ingesting documents...[/bold]")
    try:
        with console.status("[bold]Loading embedding model (first run downloads ~80MB)...[/bold]"):
            retriever = _build_retriever()
        doc_count = len(list(SAMPLE_DOCS_DIR.glob("*.md")))
        console.print(f"[green]Indexed documents from {doc_count} files[/green]\n")
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        console.print(f"[red]Ingestion failed: {e}[/red]")
        return

    agent = AgenticRAG(MODEL, retriever, token_tracker)

    while True:
        console.print("[bold green]You:[/bold green] ", end="")
        user_input = input().strip()

        if user_input.lower() in ["quit", "exit", ""]:
            console.print("\n[yellow]Ending session...[/yellow]")
            break

        try:
            response = agent.chat(user_input, console)

            console.print("\n[bold blue]Agent:[/bold blue]")
            console.print(Markdown(response))
            console.print()

        except Exception as e:
            logger.error("Error during chat: %s", e)
            console.print(f"\n[red]Error: {e}[/red]")
            break

    # Final token report
    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
