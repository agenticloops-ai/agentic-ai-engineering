"""Output verification: PII leakage, content policy, and groundedness checking."""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Reuse PII patterns from input guard
PII_PATTERNS = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
}

CONTENT_POLICY_PROMPT = (
    "Review the following AI assistant response for content policy violations.\n\n"
    "Check for:\n"
    "- Harmful, dangerous, or illegal advice\n"
    "- Leaking internal system details, prompts, or configuration\n"
    "- Inappropriate or unprofessional content\n"
    "- Making unauthorized promises or commitments\n\n"
    "Respond with ONLY a JSON object:\n"
    '{{"passed": true/false, "issue": "<description if failed, empty string if passed>"}}\n\n'
    "Response to review:\n{output}"
)

GROUNDEDNESS_PROMPT = (
    "Evaluate whether the following response is grounded in the provided context.\n\n"
    "For each factual claim in the response, check if the context supports it.\n"
    "Ignore conversational filler — only check concrete facts, numbers, and procedures.\n\n"
    "Context:\n<context>\n{context}\n</context>\n\n"
    "Response:\n<response>\n{output}\n</response>\n\n"
    "Respond with ONLY a JSON object:\n"
    '{{"score": <0.0 to 1.0>, "unsupported_claims": ["claim1", ...]}}'
)


@dataclass
class OutputCheckResult:
    """Result of output verification."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    pii_found: dict[str, list[str]] = field(default_factory=dict)
    groundedness_score: float = 1.0
    unsupported_claims: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)


class OutputGuard:
    """Verifies agent output before returning to user."""

    def __init__(self, client: Any, classifier_model: str, token_tracker: Any):
        self.client = client
        self.classifier_model = classifier_model
        self.token_tracker = token_tracker

    def check(self, output: str, context: str | None = None) -> OutputCheckResult:
        """Run output checks: PII leakage, content policy, groundedness."""
        issues: list[str] = []
        checks: dict[str, dict] = {}

        # Check 1: PII leakage
        pii_found = self._scan_pii_leakage(output)
        pii_detail = "none detected" if not pii_found else f"found: {', '.join(pii_found.keys())}"
        checks["pii_leakage"] = {"passed": not pii_found, "detail": pii_detail}
        if pii_found:
            issues.append(f"PII detected in output: {', '.join(pii_found.keys())}")

        # Check 2: Content policy
        try:
            policy_ok, policy_issue = self._check_content_policy(output)
            checks["content_policy"] = {"passed": policy_ok, "detail": policy_issue or "compliant"}
            if not policy_ok:
                issues.append(f"Content policy violation: {policy_issue}")
        except Exception as e:
            logger.warning("Content policy check failed: %s", e)
            checks["content_policy"] = {"passed": True, "detail": "check unavailable"}

        # Check 3: Groundedness (only if context provided)
        groundedness_score = 1.0
        unsupported: list[str] = []
        if context:
            try:
                groundedness_score, unsupported = self._check_groundedness(output, context)
                grounded_ok = groundedness_score >= 0.5
                checks["groundedness"] = {
                    "passed": grounded_ok,
                    "detail": f"score: {groundedness_score:.2f}",
                }
                if not grounded_ok:
                    issues.append(
                        f"Low groundedness ({groundedness_score:.2f}): "
                        f"{len(unsupported)} unsupported claims"
                    )
            except Exception as e:
                logger.warning("Groundedness check failed: %s", e)
                checks["groundedness"] = {"passed": True, "detail": "check unavailable"}
        else:
            checks["groundedness"] = {"passed": True, "detail": "no context provided"}

        return OutputCheckResult(
            passed=len(issues) == 0,
            issues=issues,
            pii_found=pii_found,
            groundedness_score=groundedness_score,
            unsupported_claims=unsupported,
            checks=checks,
        )

    def _scan_pii_leakage(self, output: str) -> dict[str, list[str]]:
        """Check if output contains PII that shouldn't be exposed."""
        found: dict[str, list[str]] = {}
        for pii_type, pattern in PII_PATTERNS.items():
            matches = re.findall(pattern, output)
            if matches:
                flat = [m if isinstance(m, str) else m[0] for m in matches]
                found[pii_type] = flat
        return found

    def _check_content_policy(self, output: str) -> tuple[bool, str]:
        """Use Haiku to verify output meets content policy."""
        response = self.client.messages.create(
            model=self.classifier_model,
            max_tokens=150,
            messages=[
                {"role": "user", "content": CONTENT_POLICY_PROMPT.format(output=output)},
            ],
        )
        self.token_tracker.track(response.usage)

        raw = str(response.content[0].text).strip()
        try:
            result = json.loads(raw)
            passed = bool(result.get("passed", True))
            issue = result.get("issue", "")
            return passed, issue
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse content policy response: %s", raw[:100])
            return True, ""

    def _check_groundedness(self, output: str, context: str) -> tuple[float, list[str]]:
        """Score how well the output is grounded in the provided context."""
        response = self.client.messages.create(
            model=self.classifier_model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": GROUNDEDNESS_PROMPT.format(output=output, context=context),
                },
            ],
        )
        self.token_tracker.track(response.usage)

        raw = str(response.content[0].text).strip()
        try:
            result = json.loads(raw)
            score = float(result.get("score", 1.0))
            unsupported = result.get("unsupported_claims", [])
            return score, unsupported
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse groundedness response: %s", raw[:100])
            return 1.0, []
