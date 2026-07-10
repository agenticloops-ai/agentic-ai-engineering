---
name: code-reviewer
description: Review Python code for correctness bugs, style issues, and missing error handling. Use when the user asks for a code review or to critique a file.
---

# Code Reviewer

Review Python code methodically and report findings ranked most-severe first.

## Procedure

1. Read the target file(s) before commenting.
2. Check, in order:
   - **Correctness** — off-by-one errors, wrong operators, unhandled `None`, mutable default arguments.
   - **Error handling** — bare `except`, swallowed exceptions, missing timeouts on I/O.
   - **Style** — PEP 8, naming, functions doing more than one thing.
3. For each finding report: `file:line — <one-sentence problem> — <concrete fix>`.
4. If nothing is wrong, say so plainly. Do not invent findings.

## Output format

Group findings under `### Correctness`, `### Error handling`, `### Style`.
Skip empty groups. End with a one-line verdict: SHIP or NEEDS WORK.
