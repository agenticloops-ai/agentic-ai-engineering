---
name: bug-triage
description: Triage bug reports against a codebase. Use when asked to triage, investigate, or classify reported issues.
---

# Bug Triage

## Steps

1. List the open issues.
2. Delegate each issue to its own subagent. Its brief must include the report's full text and ask it to reproduce the behaviour by running code, then report the root cause with a file and function name.
3. Check each result against `references/severity.md`.
4. Record every verdict in the tracker.
5. Finish with a table of issue, verdict, severity, and root cause.

A report describing intended behaviour is `not-a-bug`, even if the reporter is unhappy about it. Check the docstrings before deciding.
