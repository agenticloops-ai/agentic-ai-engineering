"""
Shared knowledge base, tool definitions, system prompt, and search function.

Used by all benchmark scripts in this tutorial module.
"""

from typing import Any

from common import setup_logging

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Knowledge base (shared research assistant corpus)
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE = [
    {
        "id": "doc_001",
        "title": "Microservices Architecture",
        "content": (
            "Microservices architecture decomposes applications into small, "
            "independent services. Each service runs in its own process, "
            "communicates via APIs, and can be deployed independently. "
            "Benefits include scalability, fault isolation, and technology "
            "flexibility. Challenges include distributed system complexity, "
            "data consistency, and operational overhead."
        ),
        "tags": ["architecture", "microservices", "distributed-systems"],
    },
    {
        "id": "doc_002",
        "title": "REST API Design",
        "content": (
            "REST APIs follow resource-oriented design principles. "
            "Use nouns for endpoints, HTTP methods for actions, and "
            "status codes for results. Best practices include versioning, "
            "pagination for collections, and consistent error response "
            "formats."
        ),
        "tags": ["api", "rest", "design"],
    },
    {
        "id": "doc_003",
        "title": "Database Indexing",
        "content": (
            "Database indexes improve query performance by creating "
            "efficient lookup structures. B-tree indexes handle equality "
            "and range queries. Composite indexes support multi-column "
            "queries but column order matters. Over-indexing slows writes "
            "and wastes storage."
        ),
        "tags": ["database", "performance", "indexing"],
    },
    {
        "id": "doc_004",
        "title": "Authentication and Authorization",
        "content": (
            "Authentication verifies identity, authorization controls "
            "access. JWT tokens enable stateless authentication. "
            "OAuth 2.0 provides delegated access. Always hash passwords "
            "with bcrypt or argon2."
        ),
        "tags": ["security", "authentication", "authorization"],
    },
    {
        "id": "doc_005",
        "title": "CI/CD Pipelines",
        "content": (
            "CI automatically builds and tests code on every commit. "
            "CD automatically deploys passing builds. Key practices: "
            "fast feedback loops, trunk-based development, feature "
            "flags, and automated rollback."
        ),
        "tags": ["devops", "ci-cd", "automation"],
    },
    {
        "id": "doc_006",
        "title": "Container Orchestration with Kubernetes",
        "content": (
            "Kubernetes manages containerized workloads. Core concepts: "
            "Pods, Services, Deployments, ConfigMaps/Secrets. Key "
            "features: auto-scaling, self-healing, rolling updates, "
            "service discovery."
        ),
        "tags": ["devops", "kubernetes", "containers"],
    },
    {
        "id": "doc_007",
        "title": "Event-Driven Architecture",
        "content": (
            "Event-driven architecture uses events to trigger "
            "communication between services. Patterns: event sourcing, "
            "CQRS, pub/sub. Benefits: loose coupling, scalability, "
            "audit trails."
        ),
        "tags": ["architecture", "events", "messaging"],
    },
    {
        "id": "doc_008",
        "title": "Caching Strategies",
        "content": (
            "Caching reduces latency by storing frequently accessed "
            "data in memory. Strategies: cache-aside, write-through, "
            "write-behind. Use Redis or Memcached for distributed "
            "caching."
        ),
        "tags": ["performance", "caching", "redis"],
    },
]

SYSTEM_PROMPT = (
    "You are a research assistant. Answer questions using ONLY the information from the "
    "search results provided via tools. Always cite your sources by document ID. "
    "If no relevant information is found, say so clearly. Do not make up information."
)

# Anthropic tool format
TOOLS_ANTHROPIC = [
    {
        "name": "search_knowledge_base",
        "description": "Search the knowledge base for documents matching a query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max documents to return",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
]

# OpenAI tool format
TOOLS_OPENAI = [
    {
        "type": "function",
        "name": "search_knowledge_base",
        "description": "Search the knowledge base for documents matching a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max documents to return",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
]

# ---------------------------------------------------------------------------
# Benchmark tasks (golden dataset subset)
# ---------------------------------------------------------------------------

BENCHMARK_TASKS = [
    {
        "id": "bench_001",
        "question": "What are the key benefits of microservices architecture?",
        "expected_keywords": ["scalability", "fault isolation", "independent"],
        "category": "architecture",
    },
    {
        "id": "bench_002",
        "question": "How should REST API endpoints be designed?",
        "expected_keywords": ["nouns", "http methods", "status codes"],
        "category": "api",
    },
    {
        "id": "bench_003",
        "question": "What strategies exist for database indexing?",
        "expected_keywords": ["b-tree", "composite", "query performance"],
        "category": "database",
    },
    {
        "id": "bench_004",
        "question": "Explain the difference between authentication and authorization.",
        "expected_keywords": ["identity", "access", "jwt", "oauth"],
        "category": "security",
    },
    {
        "id": "bench_005",
        "question": "What are the key practices in CI/CD?",
        "expected_keywords": ["continuous", "automated", "feedback"],
        "category": "devops",
    },
]

# ---------------------------------------------------------------------------
# Knowledge base search utility
# ---------------------------------------------------------------------------


def search_knowledge_base(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    """Search knowledge base using keyword matching."""
    query_words = set(query.lower().split())
    scored: list[tuple[int, dict[str, Any]]] = []
    for doc in KNOWLEDGE_BASE:
        text = f"{doc['title']} {doc['content']} {' '.join(doc['tags'])}".lower()
        score = sum(1 for word in query_words if word in text)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:max_results]]


def score_answer(answer: str, expected_keywords: list[str]) -> float:
    """Score an answer based on expected keyword coverage."""
    answer_lower = answer.lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return found / len(expected_keywords) if expected_keywords else 1.0
