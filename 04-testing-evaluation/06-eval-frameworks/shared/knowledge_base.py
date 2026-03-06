"""
Shared knowledge base and research assistant for eval framework tutorials.

Provides a simple research assistant with simulated responses so the tutorials
can focus on framework-specific evaluation patterns without requiring API keys.
"""

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
            "include scalability, fault isolation, and technology flexibility."
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
            "order matters. Over-indexing slows writes and wastes storage."
        ),
        "tags": ["database", "performance", "indexing"],
    },
    {
        "id": "doc_004",
        "title": "Authentication and Authorization",
        "content": (
            "Authentication verifies identity, authorization controls access. "
            "JWT tokens enable stateless authentication. OAuth 2.0 provides "
            "delegated access. Always hash passwords with bcrypt or argon2."
        ),
        "tags": ["security", "authentication", "authorization"],
    },
]

# Eval dataset: questions with expected answers and metadata
EVAL_TASKS = [
    {
        "id": "task_001",
        "question": "What are the key benefits of microservices architecture?",
        "reference_answer": (
            "Key benefits include scalability, fault isolation, and "
            "independent deployment of services (doc_001)."
        ),
        "expected_keywords": ["scalability", "fault isolation", "independent"],
        "expected_source_ids": ["doc_001"],
    },
    {
        "id": "task_002",
        "question": "What are the best practices for REST API design?",
        "reference_answer": (
            "Use nouns for endpoints, HTTP methods for actions, proper "
            "status codes, versioning, and pagination (doc_002)."
        ),
        "expected_keywords": ["nouns", "endpoints", "HTTP methods", "status codes"],
        "expected_source_ids": ["doc_002"],
    },
    {
        "id": "task_003",
        "question": "How do database indexes improve query performance?",
        "reference_answer": (
            "Indexes use B-tree structures for efficient lookup, reducing "
            "full table scans and speeding up queries (doc_003)."
        ),
        "expected_keywords": ["B-tree", "lookup", "query"],
        "expected_source_ids": ["doc_003"],
    },
    {
        "id": "task_004",
        "question": "What is the difference between authentication and authorization?",
        "reference_answer": (
            "Authentication verifies identity; authorization controls "
            "access permissions. Use JWT and hash passwords with bcrypt (doc_004)."
        ),
        "expected_keywords": ["identity", "access", "authentication", "authorization"],
        "expected_source_ids": ["doc_004"],
    },
    {
        "id": "task_005",
        "question": "What is the best programming language for machine learning?",
        "reference_answer": (
            "The knowledge base does not contain information about "
            "machine learning programming languages."
        ),
        "expected_keywords": [],
        "expected_source_ids": [],
    },
]

# Simulated agent responses (used by all framework tutorials)
SIMULATED_RESPONSES: dict[str, dict[str, Any]] = {
    "task_001": {
        "answer": (
            "Based on doc_001, the key benefits of microservices architecture "
            "include scalability, fault isolation, and the ability to deploy "
            "services independently."
        ),
        "tool_calls": [{"name": "search_knowledge_base", "input": {"query": "microservices"}}],
        "sources": ["doc_001"],
    },
    "task_002": {
        "answer": (
            "According to doc_002, REST API best practices include using nouns "
            "for endpoints, HTTP methods for actions, proper status codes, "
            "versioning, and pagination."
        ),
        "tool_calls": [{"name": "search_knowledge_base", "input": {"query": "REST API"}}],
        "sources": ["doc_002"],
    },
    "task_003": {
        "answer": (
            "Per doc_003, database indexes improve query performance via "
            "efficient B-tree lookup structures for equality and range queries."
        ),
        "tool_calls": [{"name": "search_knowledge_base", "input": {"query": "database indexes"}}],
        "sources": ["doc_003"],
    },
    "task_004": {
        "answer": (
            "Authentication verifies identity while authorization controls "
            "access. JWT tokens provide stateless authentication. Hash "
            "passwords with bcrypt (doc_004)."
        ),
        "tool_calls": [{"name": "search_knowledge_base", "input": {"query": "auth"}}],
        "sources": ["doc_004"],
    },
    "task_005": {
        "answer": (
            "I was unable to find any relevant information about machine "
            "learning programming languages in the knowledge base."
        ),
        "tool_calls": [{"name": "search_knowledge_base", "input": {"query": "machine learning"}}],
        "sources": [],
    },
}


def get_agent_response(task_id: str) -> dict[str, Any]:
    """Return a simulated agent response for a given task ID."""
    return SIMULATED_RESPONSES.get(
        task_id,
        {"answer": "No response available.", "tool_calls": [], "sources": []},
    )


def search_knowledge_base(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    """Search knowledge base by keyword matching."""
    query_terms = query.lower().split()
    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in KNOWLEDGE_BASE:
        searchable = f"{doc['title']} {doc['content']} {' '.join(doc['tags'])}".lower()
        score = sum(1 for term in query_terms if term in searchable)
        if score > 0:
            scored.append((score, {"id": doc["id"], "title": doc["title"], "score": score}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:max_results]]
