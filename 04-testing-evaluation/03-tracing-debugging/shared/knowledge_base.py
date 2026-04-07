"""
Shared knowledge base, tool definitions, and tool execution logic.

Used by the traced research assistant across tracing tutorials.
"""

from collections.abc import Callable
from typing import Any

from common import setup_logging

logger = setup_logging(__name__)

KNOWLEDGE_BASE = [
    {
        "id": "doc_001",
        "title": "Microservices Architecture",
        "content": (
            "Microservices architecture decomposes applications into small, "
            "independent services. Each service runs in its own process, "
            "communicates via APIs, and can be deployed independently. Benefits "
            "include scalability, fault isolation, and technology flexibility. "
            "Challenges include distributed system complexity, data consistency, "
            "and operational overhead."
        ),
        "tags": ["architecture", "microservices", "distributed-systems"],
    },
    {
        "id": "doc_002",
        "title": "REST API Design",
        "content": (
            "REST APIs follow resource-oriented design principles. Use nouns "
            "for endpoints, HTTP methods for actions, and status codes for "
            "results. Best practices include versioning, pagination for "
            "collections, and consistent error response formats."
        ),
        "tags": ["api", "rest", "design"],
    },
    {
        "id": "doc_003",
        "title": "Database Indexing",
        "content": (
            "Database indexes improve query performance by creating efficient "
            "lookup structures. B-tree indexes handle equality and range "
            "queries. Composite indexes support multi-column queries but column "
            "order matters. Over-indexing slows writes and wastes storage. Use "
            "EXPLAIN to analyze query plans."
        ),
        "tags": ["database", "performance", "indexing"],
    },
    {
        "id": "doc_004",
        "title": "Authentication and Authorization",
        "content": (
            "Authentication verifies identity, authorization controls access. "
            "JWT tokens enable stateless authentication. OAuth 2.0 provides "
            "delegated access. Always hash passwords with bcrypt or argon2. "
            "Implement rate limiting and account lockout."
        ),
        "tags": ["security", "authentication", "authorization"],
    },
    {
        "id": "doc_005",
        "title": "CI/CD Pipelines",
        "content": (
            "CI automatically builds and tests code on every commit. CD "
            "automatically deploys passing builds. Key practices: fast feedback "
            "loops, trunk-based development, feature flags, and automated "
            "rollback."
        ),
        "tags": ["devops", "ci-cd", "automation"],
    },
    {
        "id": "doc_006",
        "title": "Container Orchestration with Kubernetes",
        "content": (
            "Kubernetes manages containerized workloads. Core concepts: Pods, "
            "Services, Deployments, ConfigMaps/Secrets. Key features: "
            "auto-scaling, self-healing, rolling updates, service discovery."
        ),
        "tags": ["devops", "kubernetes", "containers"],
    },
    {
        "id": "doc_007",
        "title": "Event-Driven Architecture",
        "content": (
            "Event-driven architecture uses events to trigger communication "
            "between services. Patterns: event sourcing, CQRS, pub/sub. "
            "Benefits: loose coupling, scalability, audit trails. Challenges: "
            "eventual consistency, event ordering."
        ),
        "tags": ["architecture", "events", "messaging"],
    },
    {
        "id": "doc_008",
        "title": "Caching Strategies",
        "content": (
            "Caching reduces latency by storing frequently accessed data in "
            "memory. Strategies: cache-aside, write-through, write-behind. Use "
            "Redis or Memcached. Set appropriate TTLs and implement cache "
            "invalidation."
        ),
        "tags": ["performance", "caching", "redis"],
    },
]

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "Search the knowledge base for documents matching a query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Max results", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_document",
        "description": "Retrieve a specific document by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string", "description": "Document ID"}},
            "required": ["doc_id"],
        },
    },
]

SYSTEM_PROMPT = (
    "You are a research assistant. Use the search_knowledge_base and get_document tools "
    "to find information before answering. Always ground your answers in the documents found. "
    "If no relevant documents are found, say so."
)


def search_knowledge_base(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    """Search knowledge base by matching query terms against titles, content, and tags."""
    query_terms = query.lower().split()
    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in KNOWLEDGE_BASE:
        searchable = f"{doc['title']} {doc['content']} {' '.join(doc['tags'])}".lower()
        score = sum(1 for term in query_terms if term in searchable)
        if score > 0:
            scored.append((score, {"id": doc["id"], "title": doc["title"], "score": score}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:max_results]]


def get_document(doc_id: str) -> dict[str, Any]:
    """Retrieve a document by ID."""
    for doc in KNOWLEDGE_BASE:
        if doc["id"] == doc_id:
            return doc
    return {"error": f"Document not found: {doc_id}"}


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "search_knowledge_base": search_knowledge_base,
    "get_document": get_document,
}


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> Any:
    """Execute a tool and return its result."""
    if tool_name not in TOOL_FUNCTIONS:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return TOOL_FUNCTIONS[tool_name](**tool_input)
    except Exception as e:
        logger.error("Tool execution error: %s", e)
        return {"error": str(e)}
