"""
Code-Based Graders for Agent Evaluation

Demonstrates deterministic evaluation of agent responses using code-based graders:
keyword matching, regex patterns, source citation verification, and tool-call checks.
Runs the research assistant against a golden dataset and scores each response.
"""

import json
import os
from pathlib import Path
from typing import Any

import anthropic
from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shared.agent import ResearchAssistant
from shared.graders import (
    GraderResult,
    KeywordGrader,
    RegexGrader,
    SourceCitationGrader,
    ToolCallGrader,
)
from shared.knowledge_base import KNOWLEDGE_BASE

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Simulated responses for demo mode (when no API key is available)
# ---------------------------------------------------------------------------

SIMULATED_RESPONSES: dict[str, dict[str, Any]] = {
    "task_001": {
        "answer": (
            "Based on the search results (doc_001), microservices "
            "architecture offers several key benefits: scalability, "
            "fault isolation, and technology flexibility. Each "
            "service can be deployed independently and runs in its "
            "own process."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "microservices benefits"},
                "results": [KNOWLEDGE_BASE[0]],
            }
        ],
        "sources": [[KNOWLEDGE_BASE[0]]],
    },
    "task_002": {
        "answer": (
            "According to doc_002, REST API best practices include: "
            "use nouns for endpoints like /users and /orders, use "
            "HTTP methods for actions (GET, POST, PUT, DELETE), use "
            "proper status codes, implement versioning, and use "
            "pagination for collections."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "REST API design"},
                "results": [KNOWLEDGE_BASE[1]],
            }
        ],
        "sources": [[KNOWLEDGE_BASE[1]]],
    },
    "task_003": {
        "answer": (
            "Per doc_003, database indexes improve query "
            "performance by creating efficient lookup structures. "
            "B-tree indexes handle equality and range queries. Use "
            "EXPLAIN to analyze query plans."
        ),
        "tool_calls": [
            {
                "name": "search_knowledge_base",
                "input": {"query": "database indexes performance"},
                "results": [KNOWLEDGE_BASE[2]],
            }
        ],
        "sources": [[KNOWLEDGE_BASE[2]]],
    },
}


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------


def load_golden_tasks(path: str) -> list[dict[str, Any]]:
    """Load evaluation tasks from a JSON dataset file."""
    with Path(path).open(encoding="utf-8") as f:
        data = json.load(f)
    logger.info("Loaded %d tasks from %s (v%s)", len(data["tasks"]), path, data["version"])
    tasks: list[dict[str, Any]] = data["tasks"]
    return tasks


def evaluate_task(
    task: dict[str, Any],
    agent_response: dict[str, Any],
    keyword_grader: KeywordGrader,
    citation_grader: SourceCitationGrader,
    tool_grader: ToolCallGrader,
    regex_grader: RegexGrader,
) -> dict[str, GraderResult]:
    """Run all graders on a single task's agent response."""
    answer = agent_response["answer"]
    tool_calls = agent_response.get("tool_calls", [])

    results: dict[str, GraderResult] = {}
    results["keywords"] = keyword_grader.grade(answer, task["expected_keywords"])
    results["citations"] = citation_grader.grade(answer, task["expected_source_ids"])
    results["tool_calls"] = tool_grader.grade(tool_calls)

    # Regex check: answers should contain a doc_XXX citation pattern (or a refusal)
    if task["expected_source_ids"]:
        results["regex"] = regex_grader.grade(answer, r"doc_\d{3}")
    else:
        results["regex"] = regex_grader.grade(
            answer, r"(?:no relevant|not found|no information|cannot)"
        )

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run code-based graders against a golden dataset."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]Code-Based Graders[/bold cyan]\n\n"
            "Evaluates a research assistant using deterministic graders:\n"
            "keyword matching, regex, source citations, and tool-call verification.",
            title="Eval Tutorial 1",
        )
    )

    # Determine mode: live API or simulated
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if has_api_key:
        console.print("[green]API key found — running live evaluation[/green]\n")
        client = anthropic.Anthropic()
        agent = ResearchAssistant(client, KNOWLEDGE_BASE)
    else:
        console.print("[yellow]No API key — using simulated responses for demo[/yellow]\n")
        agent = None

    # Load golden dataset
    dataset_path = Path(__file__).parent / "datasets" / "golden_tasks.json"
    tasks = load_golden_tasks(str(dataset_path))

    # Instantiate graders
    keyword_grader = KeywordGrader()
    citation_grader = SourceCitationGrader()
    tool_grader = ToolCallGrader()
    regex_grader = RegexGrader()

    # Results table
    table = Table(title="Evaluation Results", show_lines=True)
    table.add_column("Task", style="cyan", width=12)
    table.add_column("Difficulty", width=8)
    table.add_column("Keywords", width=18)
    table.add_column("Citations", width=18)
    table.add_column("Tool Calls", width=18)
    table.add_column("Regex", width=18)

    total_scores: dict[str, list[float]] = {
        "keywords": [],
        "citations": [],
        "tool_calls": [],
        "regex": [],
    }

    # Limit to first few tasks in simulated mode for a concise demo
    eval_tasks = tasks[:3] if agent is None else tasks
    console.print(f"Running {len(eval_tasks)} tasks...\n")

    for task in eval_tasks:
        logger.info("Evaluating task %s: %s", task["id"], task["question"][:60])

        # Get agent response (live or simulated)
        if agent is not None:
            try:
                response = agent.answer(task["question"])
            except Exception as e:
                logger.error("Agent error on %s: %s", task["id"], e)
                response = {"answer": f"Error: {e}", "tool_calls": [], "sources": []}
        else:
            response = SIMULATED_RESPONSES.get(
                task["id"],
                {"answer": "No simulated response available.", "tool_calls": [], "sources": []},
            )

        # Grade the response
        grader_results = evaluate_task(
            task, response, keyword_grader, citation_grader, tool_grader, regex_grader
        )

        # Format results for table
        def fmt(result: GraderResult) -> str:
            icon = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
            return f"{icon} ({result.score:.0%})"

        table.add_row(
            task["id"],
            task["difficulty"],
            fmt(grader_results["keywords"]),
            fmt(grader_results["citations"]),
            fmt(grader_results["tool_calls"]),
            fmt(grader_results["regex"]),
        )

        for grader_name, result in grader_results.items():
            total_scores[grader_name].append(result.score)

    console.print(table)

    # Summary
    console.print("\n[bold]Aggregate Scores[/bold]")
    for grader_name, scores in total_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            console.print(f"  {grader_name:12s}: {avg:.0%} avg ({len(scores)} tasks)")

    # Token usage report (live mode only)
    if agent is not None:
        console.print()
        agent.token_tracker.report()


if __name__ == "__main__":
    main()
