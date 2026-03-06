"""
Shared knowledge base, tool definitions, and search functionality.

Provides the research corpus, system prompt, and Anthropic tool schema
used across all eval tutorial scripts.
"""

from typing import Any

from common import setup_logging

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Knowledge base corpus
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

# ---------------------------------------------------------------------------
# System prompt and tool definitions
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Search function
# ---------------------------------------------------------------------------


def search_knowledge_base(
    query: str, max_results: int = 3, corpus: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Search knowledge base using keyword matching."""
    docs = corpus if corpus is not None else KNOWLEDGE_BASE
    query_words = set(query.lower().split())
    scored: list[tuple[int, dict[str, Any]]] = []
    for doc in docs:
        text = f"{doc['title']} {doc['content']} {' '.join(doc['tags'])}".lower()
        score = sum(1 for word in query_words if word in text)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:max_results]]
