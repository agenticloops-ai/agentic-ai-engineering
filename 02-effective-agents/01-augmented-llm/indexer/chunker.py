"""
Code Chunker

Splits source code files into chunks suitable for embedding and semantic search.
Uses simple heuristics: Python files split on class/function definitions,
other files split by line count with overlap.
"""

from pathlib import Path
from typing import Any

from common.logging_config import setup_logging

logger = setup_logging(__name__)

# File extensions to index
INDEXABLE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
}

# Directories to skip
SKIP_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    ".git",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "vendor",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    "egg-info",
}

# Max lines per chunk for non-Python files
CHUNK_SIZE = 50
OVERLAP = 10


def collect_files(repo_path: Path) -> list[Path]:
    """Collect all indexable files from a repository."""
    files = []
    for path in repo_path.rglob("*"):
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if path.is_file() and path.suffix in INDEXABLE_EXTENSIONS:
            files.append(path)
    return sorted(files)


def chunk_python(content: str, filepath: str, repo: str) -> list[dict[str, Any]]:
    """Chunk Python files by splitting on top-level class/function definitions."""
    lines = content.split("\n")
    chunks: list[dict[str, Any]] = []
    current_chunk_start = 0

    for i, line in enumerate(lines):
        # Split on top-level definitions (no leading whitespace)
        if i > 0 and (line.startswith("class ") or line.startswith("def ")):
            chunk_content = "\n".join(lines[current_chunk_start:i]).strip()
            if chunk_content:
                chunks.append(
                    {
                        "content": chunk_content,
                        "filepath": filepath,
                        "start_line": current_chunk_start + 1,
                        "end_line": i,
                        "repo": repo,
                    }
                )
            current_chunk_start = i

    # Don't forget the last chunk
    chunk_content = "\n".join(lines[current_chunk_start:]).strip()
    if chunk_content:
        chunks.append(
            {
                "content": chunk_content,
                "filepath": filepath,
                "start_line": current_chunk_start + 1,
                "end_line": len(lines),
                "repo": repo,
            }
        )

    return chunks


def chunk_generic(content: str, filepath: str, repo: str) -> list[dict[str, Any]]:
    """Chunk non-Python files by fixed line count with overlap."""
    lines = content.split("\n")
    chunks: list[dict[str, Any]] = []

    i = 0
    while i < len(lines):
        end = min(i + CHUNK_SIZE, len(lines))
        chunk_content = "\n".join(lines[i:end]).strip()
        if chunk_content:
            chunks.append(
                {
                    "content": chunk_content,
                    "filepath": filepath,
                    "start_line": i + 1,
                    "end_line": end,
                    "repo": repo,
                }
            )
        i += CHUNK_SIZE - OVERLAP

    return chunks


def chunk_file(path: Path, repo_path: Path, repo_name: str) -> list[dict[str, Any]]:
    """Chunk a single file using the appropriate strategy."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("Could not read %s: %s", path, e)
        return []

    if not content.strip():
        return []

    # Limit very large files
    if len(content) > 100_000:
        content = content[:100_000]

    filepath = str(path.relative_to(repo_path))

    if path.suffix == ".py":
        return chunk_python(content, filepath, repo_name)
    return chunk_generic(content, filepath, repo_name)


def chunk_repository(repo_path: Path, repo_name: str) -> list[dict[str, Any]]:
    """Chunk all files in a repository."""
    files = collect_files(repo_path)
    logger.info("Found %d indexable files in %s", len(files), repo_path)

    all_chunks: list[dict[str, Any]] = []
    for path in files:
        all_chunks.extend(chunk_file(path, repo_path, repo_name))

    logger.info("Created %d chunks from %d files", len(all_chunks), len(files))
    return all_chunks
