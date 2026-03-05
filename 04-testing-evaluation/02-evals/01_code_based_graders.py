"""
Code-Based Graders for Agent Evaluation

Demonstrates deterministic evaluation of agent responses using code-based graders:
keyword matching, regex patterns, source citation verification, and tool-call checks.
Runs the research assistant against a golden dataset and scores each response.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from common import AnthropicTokenTracker, setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Knowledge base and research assistant (shared across eval tutorials)
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE = [
    {
        "id": "doc_001",
        "title": "Microservices Architecture",
        "content": (
            "Microservices architecture decomposes applications into "
            "small, independent services. Each service runs in its own "
            "process, communicates via APIs, and can be deployed "
            "independently. Benefits include scalability, fault "
            "isolation, and technology flexibility. Challenges include "
            "distributed system complexity, data consistency, and "
            "operational overhead."
        ),
        "tags": ["architecture", "microservices", "distributed-systems"],
    },
    {
        "id": "doc_002",
        "title": "REST API Design",
        "content": (
            "REST APIs follow resource-oriented design principles. "
            "Use nouns for endpoints (e.g., /users, /orders), HTTP "
            "methods for actions (GET, POST, PUT, DELETE), and status "
            "codes for results. Best practices include versioning "
            "(e.g., /v1/), pagination for collections, and consistent "
            "error response formats."
        ),
        "tags": ["api", "rest", "design"],
    },
    {
        "id": "doc_003",
        "title": "Database Indexing",
        "content": (
            "Database indexes improve query performance by creating "
            "efficient lookup structures. B-tree indexes handle "
            "equality and range queries. Composite indexes support "
            "multi-column queries but column order matters. "
            "Over-indexing slows writes and wastes storage. Use "
            "EXPLAIN to analyze query plans and identify missing "
            "indexes."
        ),
        "tags": ["database", "performance", "indexing"],
    },
    {
        "id": "doc_004",
        "title": "Authentication and Authorization",
        "content": (
            "Authentication verifies identity (who you are), "
            "authorization controls access (what you can do). JWT "
            "tokens enable stateless authentication with claims-based "
            "authorization. OAuth 2.0 provides delegated access. "
            "Always hash passwords with bcrypt or argon2. Implement "
            "rate limiting and account lockout to prevent brute force "
            "attacks."
        ),
        "tags": ["security", "authentication", "authorization"],
    },
    {
        "id": "doc_005",
        "title": "CI/CD Pipelines",
        "content": (
            "Continuous Integration (CI) automatically builds and "
            "tests code on every commit. Continuous Deployment (CD) "
            "automatically deploys passing builds to production. Key "
            "practices: fast feedback loops, trunk-based development, "
            "feature flags for gradual rollouts, and automated "
            "rollback on failure. Tools include GitHub Actions, "
            "GitLab CI, and Jenkins."
        ),
        "tags": ["devops", "ci-cd", "automation"],
    },
    {
        "id": "doc_006",
        "title": "Container Orchestration with Kubernetes",
        "content": (
            "Kubernetes manages containerized workloads across "
            "clusters. Core concepts: Pods (smallest deployable "
            "units), Services (network abstraction), Deployments "
            "(declarative updates), and ConfigMaps/Secrets "
            "(configuration). Key features include auto-scaling, "
            "self-healing, rolling updates, and service discovery."
        ),
        "tags": ["devops", "kubernetes", "containers"],
    },
    {
        "id": "doc_007",
        "title": "Event-Driven Architecture",
        "content": (
            "Event-driven architecture uses events to trigger and "
            "communicate between services. Patterns include event "
            "sourcing (storing state as events), CQRS (separating "
            "reads and writes), and pub/sub messaging. Benefits: "
            "loose coupling, scalability, audit trails. Challenges: "
            "eventual consistency, event ordering, and debugging "
            "distributed flows."
        ),
        "tags": ["architecture", "events", "messaging"],
    },
    {
        "id": "doc_008",
        "title": "Caching Strategies",
        "content": (
            "Caching reduces latency and database load by storing "
            "frequently accessed data in memory. Strategies include "
            "cache-aside (application manages cache), write-through "
            "(cache updated on writes), and write-behind (async cache "
            "writes). Use Redis or Memcached for distributed caching. "
            "Set appropriate TTLs and implement cache invalidation "
            "carefully."
        ),
        "tags": ["performance", "caching", "redis"],
    },
]

SYSTEM_PROMPT = (
    "You are a research assistant. Answer questions using ONLY the information from the "
    "search results provided via tools. Always cite your sources by document ID. "
    "If no relevant information is found, say so clearly. Do not make up information."
)

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the knowledge base for documents matching a "
            "query. Returns relevant documents with their content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant documents",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of documents to return (default: 3)",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
]

# Simulated responses for demo mode (when no API key is available)
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
# Graders — deterministic code-based checks
# ---------------------------------------------------------------------------


@dataclass
class GraderResult:
    """Result from a grader evaluation."""

    passed: bool
    score: float  # 0.0 to 1.0
    reason: str


class KeywordGrader:
    """Grades based on required keywords in the answer."""

    def grade(self, answer: str, expected_keywords: list[str]) -> GraderResult:
        """Check whether the answer contains the expected keywords."""
        answer_lower = answer.lower()
        found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
        missing = [kw for kw in expected_keywords if kw.lower() not in answer_lower]

        # Score is the fraction of expected keywords found
        score = len(found) / len(expected_keywords) if expected_keywords else 1.0
        passed = score >= 0.5

        reason = f"Found {len(found)}/{len(expected_keywords)} keywords"
        if missing:
            reason += f" (missing: {', '.join(missing)})"

        logger.debug("KeywordGrader: score=%.2f, found=%s", score, found)
        return GraderResult(passed=passed, score=score, reason=reason)


class RegexGrader:
    """Grades based on regex pattern matching."""

    def grade(self, answer: str, pattern: str) -> GraderResult:
        """Check whether the answer matches a regex pattern."""
        match = re.search(pattern, answer, re.IGNORECASE)
        passed = match is not None
        score = 1.0 if passed else 0.0
        reason = f"Pattern '{pattern}' {'matched' if passed else 'not found'}"

        logger.debug("RegexGrader: pattern=%s, passed=%s", pattern, passed)
        return GraderResult(passed=passed, score=score, reason=reason)


class SourceCitationGrader:
    """Grades whether the answer cites its sources."""

    def grade(self, answer: str, expected_source_ids: list[str]) -> GraderResult:
        """Check whether expected document IDs are cited in the answer."""
        if not expected_source_ids:
            # Out-of-scope tasks: check that the agent says it has no info
            has_refusal = bool(
                re.search(
                    r"no relevant|not found|no information|cannot find", answer, re.IGNORECASE
                )
            )
            return GraderResult(
                passed=has_refusal,
                score=1.0 if has_refusal else 0.0,
                reason="Out-of-scope: " + ("correctly refused" if has_refusal else "should refuse"),
            )

        # For in-scope tasks, check that doc IDs appear in the answer
        cited = [sid for sid in expected_source_ids if sid in answer]
        missing = [sid for sid in expected_source_ids if sid not in answer]

        score = len(cited) / len(expected_source_ids)
        passed = score >= 0.5
        reason = f"Cited {len(cited)}/{len(expected_source_ids)} sources"
        if missing:
            reason += f" (missing: {', '.join(missing)})"

        logger.debug("SourceCitationGrader: score=%.2f, cited=%s", score, cited)
        return GraderResult(passed=passed, score=score, reason=reason)


class ToolCallGrader:
    """Grades whether the agent made expected tool calls."""

    def grade(
        self, tool_calls: list[dict[str, Any]], expected_tool: str = "search_knowledge_base"
    ) -> GraderResult:
        """Verify the agent called the expected tool at least once."""
        tool_names = [tc.get("name", "") for tc in tool_calls]
        called = expected_tool in tool_names
        score = 1.0 if called else 0.0

        reason = (
            f"Tool '{expected_tool}' was called ({len(tool_calls)} total calls)"
            if called
            else f"Tool '{expected_tool}' was NOT called"
        )

        logger.debug("ToolCallGrader: tool=%s, called=%s", expected_tool, called)
        return GraderResult(passed=called, score=score, reason=reason)


# ---------------------------------------------------------------------------
# Research assistant
# ---------------------------------------------------------------------------


class ResearchAssistant:
    """Research assistant that searches a knowledge base and synthesizes answers."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        knowledge_base: list[dict[str, Any]],
        model: str = "claude-sonnet-4-5-20250929",
    ) -> None:
        self.client = client
        self.knowledge_base = knowledge_base
        self.model = model
        self.token_tracker = AnthropicTokenTracker()

    def search_knowledge_base(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        """Search knowledge base using keyword matching."""
        query_words = set(query.lower().split())
        scored: list[tuple[int, dict[str, Any]]] = []
        for doc in self.knowledge_base:
            text = f"{doc['title']} {doc['content']} {' '.join(doc['tags'])}".lower()
            score = sum(1 for word in query_words if word in text)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:max_results]]

    def answer(self, question: str) -> dict[str, Any]:
        """Answer a question using the knowledge base."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        tool_calls_made: list[dict[str, Any]] = []

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            self.token_tracker.track(response.usage)

            if response.stop_reason != "tool_use":
                answer_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        answer_text += block.text
                return {
                    "answer": answer_text,
                    "tool_calls": tool_calls_made,
                    "sources": [tc["results"] for tc in tool_calls_made],
                }

            # Process tool calls
            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self.search_knowledge_base(**block.input)
                    tool_calls_made.append(
                        {"name": block.name, "input": block.input, "results": result}
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})


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
