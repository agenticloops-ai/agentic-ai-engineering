"""
Memory Tools

Tools for saving and recalling persistent memories across sessions.
"""

from typing import Any

from store.memory import MemoryStore

from common.logging_config import setup_logging

logger = setup_logging(__name__)

# Tool definitions for the Anthropic API
MEMORY_TOOLS = [
    {
        "name": "save_memory",
        "description": (
            "Save information to persistent memory for future sessions. "
            "Use this to remember architectural insights, user preferences, or important facts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["facts", "insights", "preferences"],
                    "description": "Category: facts, insights, or preferences",
                },
                "content": {
                    "type": "string",
                    "description": "The information to save",
                },
            },
            "required": ["category", "content"],
        },
    },
    {
        "name": "recall_memory",
        "description": "Retrieve stored memories, optionally filtered by a keyword query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional keyword to filter memories",
                },
            },
        },
    },
]


def execute_save_memory(memory: MemoryStore, tool_input: dict[str, Any]) -> str:
    """Execute the save_memory tool."""
    return memory.save(
        category=tool_input["category"],
        content=tool_input["content"],
    )


def execute_recall_memory(memory: MemoryStore, tool_input: dict[str, Any]) -> str:
    """Execute the recall_memory tool."""
    query = tool_input.get("query")
    memories = memory.recall(query)
    if not memories:
        return "No memories found." + (f" (filter: '{query}')" if query else "")

    parts = []
    for category, entries in memories.items():
        parts.append(f"\n## {category.title()}")
        for entry in entries:
            parts.append(f"- {entry['content']} ({entry['created'][:10]})")
    return "\n".join(parts)
