"""
Tool schemas, web search configuration, and tool executor.

Uses Anthropic's tool_choice to force structured JSON responses — same technique
as tutorials 03 (routing), 05 (orchestrator), and 06 (evaluator). Server-side
web_search tool handles real-time research.
"""

import json
from typing import Any

from common import setup_logging

logger = setup_logging(__name__)

# ─── Web Search ──────────────────────────────────────────────────────────────

# Anthropic server-side web search — Claude decides when to search
# max_uses controls searches per phase to keep token costs bounded
WEB_SEARCH_TOOL: dict = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 1,
}

# ─── Classification ──────────────────────────────────────────────────────────

CLASSIFY_TOOLS: list[dict] = [
    {
        "name": "classify_content",
        "description": "Classify a content request into type, topic, and key aspects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content_type": {
                    "type": "string",
                    "enum": ["blog", "tutorial", "concept"],
                    "description": (
                        "blog: opinion pieces, experience sharing, lessons learned. "
                        "tutorial: step-by-step guides, how-to content. "
                        "concept: deep explanations of ideas, patterns, technologies."
                    ),
                },
                "topic": {
                    "type": "string",
                    "description": "Core subject matter in a few words",
                },
                "key_aspects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-3 specific angles to cover",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of the classification choice",
                },
            },
            "required": ["content_type", "topic", "key_aspects", "reasoning"],
        },
    }
]

# ─── Planning ────────────────────────────────────────────────────────────────

PLANNING_TOOLS: list[dict] = [
    {
        "name": "create_research_plan",
        "description": "Break a topic into focused research subtopics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subtopics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "research_prompt": {
                                "type": "string",
                                "description": "Focused research question",
                            },
                        },
                        "required": ["title", "research_prompt"],
                    },
                    "description": "2-3 subtopics to research in parallel",
                },
            },
            "required": ["subtopics"],
        },
    }
]

# ─── Evaluation ──────────────────────────────────────────────────────────────

EVALUATION_TOOLS: list[dict] = [
    {
        "name": "evaluate_draft",
        "description": "Evaluate a draft on multiple quality dimensions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clarity": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "technical_accuracy": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "structure": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "engagement": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "human_voice": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Does it sound like a real person?",
                },
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific issues found",
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Actionable improvement suggestions",
                },
            },
            "required": [
                "clarity",
                "technical_accuracy",
                "structure",
                "engagement",
                "human_voice",
                "issues",
                "suggestions",
            ],
        },
    }
]

# ─── SEO Title Evaluation ────────────────────────────────────────────────────

SEO_EVALUATION_TOOLS: list[dict] = [
    {
        "name": "pick_best_title",
        "description": "Evaluate SEO title candidates and pick the best one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "winning_index": {
                    "type": "integer",
                    "description": "0-based index of the best title",
                },
                "winning_title": {
                    "type": "string",
                    "description": "The selected best title",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this title is the best SEO choice",
                },
            },
            "required": ["winning_index", "winning_title", "reasoning"],
        },
    }
]


# ─── Tool Executor ──────────────────────────────────────────────────────────


class ToolExecutor:
    """Executes user-defined tools. Server-side tools (web_search) are handled by Anthropic."""

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Dispatch a tool call. Add custom tools here."""
        logger.warning("Unknown tool: %s", tool_name)
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
