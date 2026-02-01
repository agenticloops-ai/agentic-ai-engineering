"""
Repository Tools

Tools for cloning GitHub repositories and managing indexed codebases.
"""

import subprocess
from pathlib import Path
from typing import Any

from indexer.chunker import chunk_repository, collect_files
from indexer.embedder import Embedder, index_chunks
from store.vector import VectorStore

from common.logging_config import setup_logging

logger = setup_logging(__name__)

# Where cloned repos are stored
REPOS_DIR = Path(__file__).parent.parent / "repos"

REPO_TOOLS = [
    {
        "name": "clone_and_index",
        "description": (
            "Clone a GitHub repository and index it for semantic search. "
            "Provide either a GitHub repo like 'pallets/flask' or a local path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "GitHub repo (owner/repo) or local path",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "list_repos",
        "description": "List all indexed repositories with their chunk counts.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _normalize_collection_name(repo: str) -> str:
    """Convert repo identifier to a valid ChromaDB collection name."""
    # ChromaDB requires: 3-63 chars, starts/ends with alphanumeric, only alphanumeric/underscore/hyphen
    name = repo.replace("/", "-").replace(".", "-").replace(" ", "-")
    # Ensure it starts with alphanumeric
    if name and not name[0].isalnum():
        name = "r-" + name
    # Truncate to 63 chars
    return name[:63]


def _resolve_repo_path(repo: str) -> tuple[Path, str, bool]:
    """Resolve repo to a local path. Returns (path, collection_name, needs_clone)."""
    local_path = Path(repo).expanduser()
    if local_path.is_dir():
        name = "local-" + local_path.name
        return local_path, _normalize_collection_name(name), False

    # Treat as GitHub repo
    name = _normalize_collection_name(repo)
    clone_dir = REPOS_DIR / name
    return clone_dir, name, not clone_dir.exists()


def execute_clone_and_index(
    vector_store: VectorStore, embedder: Embedder, tool_input: dict[str, Any]
) -> str:
    """Clone a repo and index it for semantic search."""
    repo = tool_input["repo"]
    repo_path, collection_name, needs_clone = _resolve_repo_path(repo)

    # Check if already indexed
    if vector_store.collection_exists(collection_name):
        collections = vector_store.list_collections()
        for c in collections:
            if c["name"] == collection_name:
                return f"Repository '{repo}' is already indexed ({c['chunks']} chunks). Ready to search!"

    # Clone if needed
    if needs_clone:
        REPOS_DIR.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/{repo}.git"
        logger.info("Cloning %s to %s", url, repo_path)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(repo_path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            return f"Failed to clone '{repo}': {e.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return f"Cloning '{repo}' timed out."

    # Count files and chunk
    files = collect_files(repo_path)
    chunks = chunk_repository(repo_path, collection_name)

    if not chunks:
        return f"No indexable files found in '{repo}'."

    # Embed and store
    count = index_chunks(embedder, vector_store, collection_name, chunks)

    return (
        f"Indexed '{repo}': {len(files)} files, {count} chunks. "
        f"Ready to search! Try asking about the codebase."
    )


def execute_list_repos(vector_store: VectorStore, _tool_input: dict[str, Any]) -> str:
    """List all indexed repositories."""
    collections = vector_store.list_collections()
    if not collections:
        return "No repositories indexed yet. Use clone_and_index to add one."

    lines = ["Indexed repositories:"]
    for c in collections:
        lines.append(f"  - {c['name']}: {c['chunks']} chunks")
    return "\n".join(lines)
