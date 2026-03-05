"""Grader implementations for evaluating agent responses."""

import logging
import re

from eval_harness.models import EvalTask, EvalTrial, GraderScore

logger = logging.getLogger(__name__)


class KeywordGrader:
    """Grades based on expected keywords in the answer."""

    def grade(self, answer: str, expected_keywords: list[str]) -> GraderScore:
        """Check whether the answer contains the expected keywords."""
        if not expected_keywords:
            return GraderScore(
                grader_name="keyword",
                passed=True,
                score=1.0,
                reason="No keywords expected",
            )

        answer_lower = answer.lower()
        found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
        missing = [kw for kw in expected_keywords if kw.lower() not in answer_lower]
        score = len(found) / len(expected_keywords)
        passed = score >= 0.5

        reason = f"Found {len(found)}/{len(expected_keywords)} keywords"
        if missing:
            reason += f" (missing: {', '.join(missing)})"

        logger.debug("KeywordGrader: score=%.2f, found=%s", score, found)
        return GraderScore(grader_name="keyword", passed=passed, score=score, reason=reason)


class SourceCitationGrader:
    """Grades whether the answer cites expected sources."""

    def grade(self, answer: str, expected_source_ids: list[str]) -> GraderScore:
        """Check whether expected document IDs are cited in the answer."""
        if not expected_source_ids:
            # Out-of-scope tasks: agent should indicate no relevant info
            has_refusal = bool(
                re.search(
                    r"no relevant|not found|no information|cannot find|could not find",
                    answer,
                    re.IGNORECASE,
                )
            )
            return GraderScore(
                grader_name="citation",
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
        return GraderScore(grader_name="citation", passed=passed, score=score, reason=reason)


class CompositeGrader:
    """Combines multiple graders with configurable weights."""

    def __init__(
        self,
        keyword_weight: float = 0.5,
        citation_weight: float = 0.5,
    ) -> None:
        self.keyword_grader = KeywordGrader()
        self.citation_grader = SourceCitationGrader()
        self.keyword_weight = keyword_weight
        self.citation_weight = citation_weight

    def grade(self, trial: EvalTrial, task: EvalTask) -> list[GraderScore]:
        """Run all graders and return a list of scores."""
        scores: list[GraderScore] = []

        # Keyword grading
        keyword_score = self.keyword_grader.grade(trial.answer, task.expected_keywords)
        scores.append(keyword_score)

        # Source citation grading
        citation_score = self.citation_grader.grade(trial.answer, task.expected_source_ids)
        scores.append(citation_score)

        # Tool call grading — verify the agent used the search tool
        tool_names = [tc.get("name", "") for tc in trial.tool_calls]
        tool_called = "search_knowledge_base" in tool_names
        tool_score = GraderScore(
            grader_name="tool_call",
            passed=tool_called,
            score=1.0 if tool_called else 0.0,
            reason=(
                f"search_knowledge_base called ({len(trial.tool_calls)} total)"
                if tool_called
                else "search_knowledge_base NOT called"
            ),
        )
        scores.append(tool_score)

        # Composite score — weighted average of keyword and citation
        composite_val = (
            keyword_score.score * self.keyword_weight + citation_score.score * self.citation_weight
        )
        composite_passed = composite_val >= 0.5
        scores.append(
            GraderScore(
                grader_name="composite",
                passed=composite_passed,
                score=round(composite_val, 3),
                reason=(
                    f"Weighted: keyword({self.keyword_weight}) + "
                    f"citation({self.citation_weight}) = {composite_val:.3f}"
                ),
            )
        )

        logger.debug(
            "CompositeGrader for %s: composite=%.3f, passed=%s",
            task.id,
            composite_val,
            composite_passed,
        )
        return scores
