"""
File Tools

Tools for reading files and exploring directory structure of indexed repositories.
"""

from pathlib import Path
from typing import Any

from common.logging_config import setup_logging

logger = setup_logging(__name__)

# Where cloned repos are stored
REPOS_DIR = Path(__file__).parent.parent / "repos"

FILE_TOOLS = [
    {
        "name": "read_file",
        "description": "Read the full content of a file from an indexed repository, with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repository name (e.g., 'pallets-flask')",
                },
                "filepath": {
                    "type": "string",
                    "description": "Path to file within the repo (e.g., 'src/flask/app.py')",
                },
            },
            "required": ["repo", "filepath"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and directories at a path within an indexed repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repository name (e.g., 'pallets-flask')",
                },
                "path": {
                    "type": "string",
                    "description": "Path within repo (defaults to root)",
                    "default": "",
                },
            },
            "required": ["repo"],
        },
    },
]


def _find_repo_path(repo: str) -> Path | None:
    """Find the local path for a repository."""
    # Check repos directory
    repo_path = REPOS_DIR / repo
    if repo_path.is_dir():
        return repo_path

    # Check if it's a local- prefixed collection
    if not repo.startswith("local-"):
        repo_path = REPOS_DIR / f"local-{repo}"
        if repo_path.is_dir():
            return repo_path

    return None


def execute_read_file(_vector_store: Any, tool_input: dict[str, Any]) -> str:
    """Read a file from an indexed repository with line numbers."""
    repo = tool_input["repo"]
    filepath = tool_input["filepath"]

    repo_path = _find_repo_path(repo)
    if not repo_path:
        return f"Repository '{repo}' not found locally."

    file_path = repo_path / filepath
    if not file_path.is_file():
        return f"File not found: {filepath} in {repo}"

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Error reading file: {e}"

    # Add line numbers, truncate large files to avoid context explosion
    lines = content.split("\n")
    max_lines = 300
    truncated = len(lines) > max_lines
    display_lines = lines[:max_lines]
    numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(display_lines)]
    result = f"File: {filepath} ({len(lines)} lines)\n\n" + "\n".join(numbered)
    if truncated:
        result += f"\n\n... truncated ({len(lines) - max_lines} lines remaining)"
    return result


def execute_list_directory(_vector_store: Any, tool_input: dict[str, Any]) -> str:
    """List directory contents of an indexed repository."""
    repo = tool_input["repo"]
    subpath = tool_input.get("path", "")

    repo_path = _find_repo_path(repo)
    if not repo_path:
        return f"Repository '{repo}' not found locally."

    target = repo_path / subpath
    if not target.is_dir():
        return f"Directory not found: {subpath or '/'} in {repo}"

    entries = sorted(target.iterdir())
    lines = [f"Directory: {subpath or '/'} in {repo}\n"]

    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            lines.append(f"  📁 {entry.name}/")
        else:
            size = entry.stat().st_size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            lines.append(f"  📄 {entry.name} ({size_str})")

    return "\n".join(lines)
