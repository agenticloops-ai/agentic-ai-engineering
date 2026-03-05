"""
LLM-as-Judge Evaluation

Demonstrates using an LLM to evaluate agent responses with structured rubrics.
The judge scores accuracy, completeness, and grounding on a 1-5 scale using
tool_choice to enforce structured output.
"""

import json
import os
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
# Knowledge base and research assistant
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
# LLM-as-Judge — structured evaluation with rubrics
# ---------------------------------------------------------------------------

# The judge uses tool_choice to force structured output
JUDGE_TOOLS = [
    {
        "name": "submit_evaluation",
        "description": "Submit structured evaluation scores for an agent response.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "Chain-of-thought reasoning about the response quality",
                },
                "accuracy_score": {
                    "type": "integer",
                    "description": "1-5 accuracy score",
                    "minimum": 1,
                    "maximum": 5,
                },
                "accuracy_reason": {"type": "string"},
                "completeness_score": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                },
                "completeness_reason": {"type": "string"},
                "grounding_score": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                },
                "grounding_reason": {"type": "string"},
            },
            "required": [
                "reasoning",
                "accuracy_score",
                "accuracy_reason",
                "completeness_score",
                "completeness_reason",
                "grounding_score",
                "grounding_reason",
            ],
        },
    },
]

# Rubric given to the judge for consistent evaluation
JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for a research assistant agent.

Evaluate the agent's response using these rubrics:

**Accuracy (1-5)**
1: Major factual errors or fabricated information
2: Several inaccuracies
3: Mostly accurate with minor errors
4: Accurate with negligible issues
5: Perfectly accurate, all facts match the reference documents

**Completeness (1-5)**
1: Misses most relevant information
2: Covers less than half of relevant points
3: Covers the main points but misses some details
4: Thorough coverage with minor omissions
5: Comprehensive, covers all relevant aspects

**Grounding (1-5)**
1: No source citations at all
2: Some claims unsupported
3: Most claims cited but some gaps
4: Nearly all claims properly cited
5: Every claim is grounded in cited sources

Always use the submit_evaluation tool to provide your structured assessment."""


@dataclass
class JudgeResult:
    """Structured result from an LLM judge evaluation."""

    reasoning: str
    accuracy_score: int
    accuracy_reason: str
    completeness_score: int
    completeness_reason: str
    grounding_score: int
    grounding_reason: str

    @property
    def avg_score(self) -> float:
        """Compute the average score across all dimensions."""
        return (self.accuracy_score + self.completeness_score + self.grounding_score) / 3.0


class LLMJudge:
    """Uses an LLM to evaluate agent responses with structured rubrics."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str = "claude-sonnet-4-5-20250929",
    ) -> None:
        self.client = client
        self.model = model
        self.token_tracker = AnthropicTokenTracker()

    def evaluate(
        self,
        question: str,
        answer: str,
        reference_docs: list[dict[str, Any]],
        expected_answer: str | None = None,
    ) -> JudgeResult:
        """Evaluate an agent response using chain-of-thought judging."""
        # Build the evaluation prompt with all context the judge needs
        ref_text = json.dumps(reference_docs, indent=2)
        prompt = (
            f"## Question\n{question}\n\n"
            f"## Agent's Answer\n{answer}\n\n"
            f"## Reference Documents (ground truth)\n{ref_text}"
        )
        if expected_answer:
            prompt += f"\n\n## Expected Answer Summary\n{expected_answer}"

        logger.info("LLM judge evaluating answer (question: %s...)", question[:50])

        # Use tool_choice to force structured output via the submit_evaluation tool
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=JUDGE_SYSTEM_PROMPT,
            tools=JUDGE_TOOLS,
            tool_choice={"type": "tool", "name": "submit_evaluation"},
            messages=[{"role": "user", "content": prompt}],
        )
        self.token_tracker.track(response.usage)

        # Extract the structured evaluation from the tool call
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_evaluation":
                return JudgeResult(
                    reasoning=block.input["reasoning"],
                    accuracy_score=block.input["accuracy_score"],
                    accuracy_reason=block.input["accuracy_reason"],
                    completeness_score=block.input["completeness_score"],
                    completeness_reason=block.input["completeness_reason"],
                    grounding_score=block.input["grounding_score"],
                    grounding_reason=block.input["grounding_reason"],
                )

        # Fallback if tool call not found (should not happen with tool_choice)
        logger.warning("Judge did not return structured evaluation")
        return JudgeResult(
            reasoning="Failed to parse",
            accuracy_score=1,
            accuracy_reason="Parse error",
            completeness_score=1,
            completeness_reason="Parse error",
            grounding_score=1,
            grounding_reason="Parse error",
        )


# Simulated judge results for demo mode
SIMULATED_JUDGE_RESULTS: dict[str, JudgeResult] = {
    "task_001": JudgeResult(
        reasoning=(
            "The answer accurately identifies scalability, fault "
            "isolation, and independent deployment as key benefits, "
            "matching doc_001."
        ),
        accuracy_score=5,
        accuracy_reason="All stated benefits match the reference document exactly.",
        completeness_score=4,
        completeness_reason="Covers main benefits but omits technology flexibility detail.",
        grounding_score=5,
        grounding_reason="Properly cites doc_001 as the source.",
    ),
    "task_002": JudgeResult(
        reasoning=(
            "The answer covers nouns for endpoints, HTTP methods, "
            "status codes, versioning, and pagination from doc_002."
        ),
        accuracy_score=5,
        accuracy_reason="All facts align with doc_002.",
        completeness_score=5,
        completeness_reason="Covers all key REST API design principles.",
        grounding_score=4,
        grounding_reason="Cites doc_002 but some claims lack explicit attribution.",
    ),
    "task_003": JudgeResult(
        reasoning=(
            "Mentions B-tree indexes, lookup structures, and "
            "EXPLAIN, all from doc_003. Misses composite index "
            "details."
        ),
        accuracy_score=5,
        accuracy_reason="All stated facts are correct per doc_003.",
        completeness_score=3,
        completeness_reason="Omits composite indexes and over-indexing trade-offs.",
        grounding_score=4,
        grounding_reason="Cites doc_003 but not all claims are explicitly attributed.",
    ),
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run LLM-as-judge evaluation on research assistant responses."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]LLM-as-Judge Evaluation[/bold cyan]\n\n"
            "Uses an LLM to evaluate agent responses on three dimensions:\n"
            "accuracy, completeness, and grounding (1-5 scale each).\n"
            "Structured output is enforced via tool_choice.",
            title="Eval Tutorial 2",
        )
    )

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if has_api_key:
        console.print("[green]API key found — running live evaluation[/green]\n")
        client = anthropic.Anthropic()
        agent = ResearchAssistant(client, KNOWLEDGE_BASE)
        judge = LLMJudge(client)
    else:
        console.print("[yellow]No API key — using simulated results for demo[/yellow]\n")
        agent = None
        judge = None

    # Load a subset of tasks for this demo
    dataset_path = Path(__file__).parent / "datasets" / "golden_tasks.json"
    with dataset_path.open(encoding="utf-8") as f:
        data = json.load(f)
    tasks = data["tasks"]

    # Use first 3 tasks for demo (LLM-as-judge is expensive)
    eval_tasks = tasks[:3] if agent is None else tasks[:5]
    console.print(f"Evaluating {len(eval_tasks)} tasks with LLM-as-judge...\n")

    # Results table
    table = Table(title="LLM-as-Judge Results", show_lines=True)
    table.add_column("Task", style="cyan", width=12)
    table.add_column("Accuracy", width=10, justify="center")
    table.add_column("Completeness", width=12, justify="center")
    table.add_column("Grounding", width=10, justify="center")
    table.add_column("Avg", width=8, justify="center")
    table.add_column("Reasoning", width=50)

    all_results: list[JudgeResult] = []

    for task in eval_tasks:
        task_id = task["id"]
        logger.info("Evaluating %s with LLM judge", task_id)

        if agent is not None and judge is not None:
            try:
                response = agent.answer(task["question"])
                # Gather reference docs for the judge
                ref_docs = [
                    doc for doc in KNOWLEDGE_BASE if doc["id"] in task["expected_source_ids"]
                ]
                result = judge.evaluate(
                    question=task["question"],
                    answer=response["answer"],
                    reference_docs=ref_docs if ref_docs else KNOWLEDGE_BASE[:2],
                )
            except Exception as e:
                logger.error("Error evaluating %s: %s", task_id, e)
                result = JudgeResult(
                    reasoning=f"Error: {e}",
                    accuracy_score=1,
                    accuracy_reason="Error",
                    completeness_score=1,
                    completeness_reason="Error",
                    grounding_score=1,
                    grounding_reason="Error",
                )
        else:
            result = SIMULATED_JUDGE_RESULTS.get(
                task_id,
                JudgeResult(
                    reasoning="No simulated result",
                    accuracy_score=3,
                    accuracy_reason="N/A",
                    completeness_score=3,
                    completeness_reason="N/A",
                    grounding_score=3,
                    grounding_reason="N/A",
                ),
            )

        all_results.append(result)

        # Color-code scores
        def score_color(s: int) -> str:
            if s >= 4:
                return f"[green]{s}/5[/green]"
            if s >= 3:
                return f"[yellow]{s}/5[/yellow]"
            return f"[red]{s}/5[/red]"

        # Truncate reasoning for table display
        short_reasoning = (
            result.reasoning[:80] + "..." if len(result.reasoning) > 80 else result.reasoning
        )

        table.add_row(
            task_id,
            score_color(result.accuracy_score),
            score_color(result.completeness_score),
            score_color(result.grounding_score),
            f"{result.avg_score:.1f}",
            short_reasoning,
        )

    console.print(table)

    # Aggregate statistics
    if all_results:
        avg_accuracy = sum(r.accuracy_score for r in all_results) / len(all_results)
        avg_completeness = sum(r.completeness_score for r in all_results) / len(all_results)
        avg_grounding = sum(r.grounding_score for r in all_results) / len(all_results)
        overall = sum(r.avg_score for r in all_results) / len(all_results)

        console.print("\n[bold]Aggregate Scores[/bold]")
        console.print(f"  Accuracy:      {avg_accuracy:.2f}/5")
        console.print(f"  Completeness:  {avg_completeness:.2f}/5")
        console.print(f"  Grounding:     {avg_grounding:.2f}/5")
        console.print(f"  Overall:       {overall:.2f}/5")

    # Token usage
    if agent is not None:
        console.print("\n[bold]Token Usage[/bold]")
        console.print("[dim]Agent:[/dim]")
        agent.token_tracker.report()
    if judge is not None:
        console.print("[dim]Judge:[/dim]")
        judge.token_tracker.report()


if __name__ == "__main__":
    main()
