"""MemoryManager — orchestrates all three memory tiers."""

import json

import anthropic
from common.logging_config import setup_logging

from .episodic import EpisodicMemory
from .models import MemoryEntry, MemoryType
from .semantic import SemanticMemory
from .working import WorkingMemory

logger = setup_logging(__name__)

# Prompt for extracting important items from conversation
CONSOLIDATION_PROMPT = """\
Analyze this conversation and extract important information worth remembering long-term.
Return a JSON array of objects, each with:
- "content": the fact or event to remember (one concise sentence)
- "importance": float 0.0-1.0 (how important is this to remember?)
- "type": either "episodic" (events, interactions, things that happened) or \
"semantic" (facts, preferences, knowledge)

Only extract genuinely important information. Return an empty array [] if nothing is worth saving.

Conversation:
{conversation}

Respond with ONLY the JSON array, no other text."""


class MemoryManager:
    """Orchestrates working, episodic, and semantic memory tiers."""

    def __init__(self) -> None:
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()

    def remember(
        self,
        content: str,
        memory_type: str = "working",
        importance: float = 0.5,
        metadata: dict | None = None,
    ) -> str:
        """Store a memory in the specified tier."""
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType(memory_type),
            importance=importance,
            metadata=metadata or {},
        )

        if memory_type == "working":
            self.working.add(content, importance, metadata)
        elif memory_type == "episodic":
            self.episodic.save(entry)
        elif memory_type == "semantic":
            self.semantic.save(entry)
        else:
            return f"Unknown memory type: {memory_type}"

        return f"Remembered in {memory_type}: {content}"

    def recall(self, query: str, limit: int = 5) -> str:
        """Cross-tier search — combines episodic keyword and semantic similarity results."""
        results: list[tuple[str, str, float]] = []  # (source, content, score)

        # Episodic keyword search
        episodic_matches = self.episodic.search(query, limit=limit)
        for entry in episodic_matches:
            results.append(("episodic", entry.content, entry.importance))

        # Semantic similarity search
        semantic_matches = self.semantic.search(query, limit=limit)
        for entry, similarity in semantic_matches:
            # Rank by similarity * importance
            score = similarity * entry.importance
            results.append(("semantic", entry.content, score))

        # Sort by score descending
        results.sort(key=lambda x: x[2], reverse=True)
        results = results[:limit]

        if not results:
            return "No relevant memories found."

        lines = []
        for source, content, score in results:
            lines.append(f"[{source}] (score: {score:.2f}) {content}")
        return "\n".join(lines)

    def forget(self, memory_id: str, memory_type: str) -> str:
        """Delete a specific memory from the specified tier."""
        if memory_type == "episodic":
            success = self.episodic.delete(memory_id)
        elif memory_type == "semantic":
            success = self.semantic.delete(memory_id)
        elif memory_type == "working":
            return "Working memory clears automatically at session end."
        else:
            return f"Unknown memory type: {memory_type}"

        return f"{'Deleted' if success else 'Not found'}: {memory_id} from {memory_type}"

    def build_memory_context(self) -> str:
        """Build a memory context string for injection into the system prompt."""
        sections: list[str] = []

        # Recent episodic memories
        recent = self.episodic.get_recent(5)
        if recent:
            episodic_lines = [f"- {e.content}" for e in recent]
            sections.append("## Recent Events\n" + "\n".join(episodic_lines))

        # Top semantic memories (most relevant general knowledge)
        semantic_all = self.semantic.list_all()
        if semantic_all:
            # Sort by importance, take top entries
            top = sorted(semantic_all, key=lambda e: e.importance, reverse=True)[:5]
            semantic_lines = [f"- {e.content}" for e in top]
            sections.append("## Known Facts\n" + "\n".join(semantic_lines))

        if not sections:
            return ""

        return "# Recalled Memories\n\n" + "\n\n".join(sections)

    def consolidate(
        self,
        conversation_messages: list[dict],
        client: anthropic.Anthropic,
        model: str,
    ) -> list[str]:
        """Use LLM to extract important items from conversation into persistent memory."""
        # Build conversation text from messages
        parts: list[str] = []
        for msg in conversation_messages:
            role = msg["role"]
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(f"{role}: {content}")
            elif isinstance(content, list):
                text_parts = [
                    b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"
                ]
                if text_parts:
                    parts.append(f"{role}: {' '.join(text_parts)}")

        conversation_text = "\n".join(parts)
        if not conversation_text.strip():
            return []

        prompt = CONSOLIDATION_PROMPT.format(conversation=conversation_text)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[: -3].strip()

            # Parse JSON array from response
            items = json.loads(raw)
            if not isinstance(items, list):
                return []

        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("Consolidation failed: %s", e)
            return []

        saved: list[str] = []
        for item in items:
            content = item.get("content", "")
            importance = float(item.get("importance", 0.5))
            mem_type = item.get("type", "episodic")

            if mem_type not in ("episodic", "semantic"):
                mem_type = "episodic"

            self.remember(content, memory_type=mem_type, importance=importance)
            saved.append(f"[{mem_type}] {content}")

        logger.info("Consolidated %d memories from conversation", len(saved))
        return saved

    def get_stats(self) -> dict:
        """Aggregate statistics across all memory tiers."""
        return {
            "working": self.working.stats(),
            "episodic": self.episodic.stats(),
            "semantic": self.semantic.stats(),
        }
