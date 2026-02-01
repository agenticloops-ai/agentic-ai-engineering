"""
Search Tools

Semantic search and regex grep across indexed codebases.
"""

import re
from pathlib import Path
from typing import Any

from indexer.chunker import INDEXABLE_EXTENSIONS
from indexer.embedder import Embedder
from store.vector import VectorStore

from common.logging_config import setup_logging

logger = setup_logging(__name__)

# Where cloned repos are stored
REPOS_DIR = Path(__file__).parent.parent / "repos"

SEARCH_TOOLS = [
    {
        "name": "search_code",
        "description": (
            "Semantic search across indexed codebases. Use for conceptual questions "
            "like 'how does routing work?' or 'where is auth handled?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "repo": {
                    "type": "string",
                    "description": "Limit search to specific repo (optional)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "grep",
        "description": (
            "Exact regex pattern search across repository files. "
            "Use for finding specific identifiers, TODOs, or exact strings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "repo": {
                    "type": "string",
                    "description": "Limit search to specific repo (optional)",
                },
            },
            "required": ["pattern"],
        },
    },
]


def execute_search_code(
    vector_store: VectorStore, embedder: Embedder, tool_input: dict[str, Any]
) -> str:
    """Semantic search across indexed codebases."""
    query = tool_input["query"]
    repo = tool_input.get("repo")

    query_embedding = embedder.embed_query(query)
    results = vector_store.search(
        query_embedding=query_embedding,
        collection_name=repo,
        n_results=5,
    )

    if not results:
        return f"No results found for: {query}"

    parts = [f"Search results for: '{query}'\n"]
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        score = 1 - r["distance"]  # Convert distance to similarity
        parts.append(
            f"### Result {i} (relevance: {score:.2f})\n"
            f"**{meta['filepath']}** lines {meta['start_line']}-{meta['end_line']} "
            f"[{r['collection']}]\n"
            f"```\n{r['content'][:500]}\n```\n"
        )

    return "\n".join(parts)


def execute_grep(vector_store: VectorStore, _embedder: Embedder, tool_input: dict[str, Any]) -> str:
    """Regex search across repository files."""
    pattern = tool_input["pattern"]
    repo = tool_input.get("repo")

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    # Determine which repos to search
    if repo:
        search_dirs = [REPOS_DIR / repo]
    else:
        search_dirs = [d for d in REPOS_DIR.iterdir() if d.is_dir()] if REPOS_DIR.exists() else []

    if not search_dirs:
        return "No repositories available. Use clone_and_index first."

    matches: list[str] = []
    context_lines = 2

    for repo_dir in search_dirs:
        if not repo_dir.exists():
            continue
        for filepath in repo_dir.rglob("*"):
            if not filepath.is_file() or filepath.suffix not in INDEXABLE_EXTENSIONS:
                continue

            try:
                lines = filepath.read_text(encoding="utf-8", errors="ignore").split("\n")
            except Exception:
                continue

            for i, line in enumerate(lines):
                if regex.search(line):
                    rel_path = filepath.relative_to(repo_dir)
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    context = "\n".join(
                        f"{'>' if j == i else ' '} {j + 1:4d} | {lines[j]}"
                        for j in range(start, end)
                    )
                    matches.append(f"**{rel_path}:{i + 1}**\n```\n{context}\n```")

                    if len(matches) >= 20:
                        break
            if len(matches) >= 20:
                break
        if len(matches) >= 20:
            break

    if not matches:
        return f"No matches for pattern: {pattern}"

    header = f"Found {len(matches)} matches for `{pattern}`"
    if len(matches) >= 20:
        header += " (showing first 20)"
    return header + "\n\n" + "\n\n".join(matches)
