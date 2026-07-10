---
name: changelog
description: Write or update a project CHANGELOG entry following the Keep a Changelog format. Use when the user asks to add a changelog entry or release notes.
---

# Changelog

Produce a CHANGELOG entry in the "Keep a Changelog" style.

## Procedure

1. Read `template.md` (bundled with this skill) for the exact section layout — load it with the file-reading tool before writing.
2. Group changes under the standard headings: `Added`, `Changed`, `Fixed`, `Removed`.
3. Write each entry as a single imperative line, most user-visible change first.
4. Omit empty headings. Never fabricate a version number — ask if it is unknown.

## Rules

- Present tense, imperative mood ("Add", not "Added" in the body lines).
- Link issue/PR numbers when provided.
- Keep entries user-facing; skip internal refactors unless they change behavior.
