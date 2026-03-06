"""
Custom Promptfoo assertion for keyword coverage grading.

Promptfoo calls get_assert() for each assertion of type 'python'.
Returns a dict with pass, score, and reason.
"""


def get_assert(output, context):
    """Check keyword coverage in the agent output."""
    metadata = context.get("test", {}).get("metadata", {})
    keywords = metadata.get("keywords", [])

    if not keywords:
        return {"pass": True, "score": 1.0, "reason": "No keywords to check"}

    output_lower = output.lower()
    found = [kw for kw in keywords if kw.lower() in output_lower]
    missing = [kw for kw in keywords if kw.lower() not in output_lower]

    score = len(found) / len(keywords)
    passed = score >= 0.5

    reason = f"Found {len(found)}/{len(keywords)} keywords"
    if missing:
        reason += f" (missing: {', '.join(missing)})"

    return {"pass": passed, "score": score, "reason": reason}
