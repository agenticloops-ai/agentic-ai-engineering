"""
Code-based graders for deterministic agent evaluation.

Provides keyword matching, regex pattern matching, source citation
verification, and tool-call checking. Each grader returns a GraderResult
with pass/fail, score (0-1), and human-readable reason.
"""

import re
from dataclasses import dataclass
from typing import Any

from common import setup_logging

logger = setup_logging(__name__)


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
