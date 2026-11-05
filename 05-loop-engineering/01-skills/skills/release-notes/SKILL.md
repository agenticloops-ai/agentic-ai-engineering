---
name: release-notes
description: Turn a list of code changes into customer-facing release notes. Use when the user asks for release notes, a changelog entry, or a "what's new" summary.
---

# Release Notes

Write notes for the people who use the product, not the people who built it.

## Steps

1. Read `references/style-guide.md` for voice and wording rules.
2. Sort each change into one section: **Breaking**, **New**, **Improved**, or **Fixed**. Leave out a section that has no entries.
3. Drop changes with no effect on users, such as refactors and internal dependency upgrades.
4. Fill in `assets/template.md` and return only the finished notes.

Always put breaking changes first and say what the reader must do about them.
