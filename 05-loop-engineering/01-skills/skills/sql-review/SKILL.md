---
name: sql-review
description: Review SQL queries for performance and correctness problems. Use when the user shares a SQL query or asks why a query is slow.
---

# SQL Review

## Steps

1. Read `references/anti-patterns.md` and check the query against every entry.
2. Report each finding as: the fragment, why it hurts, and the rewritten fragment.
3. Order findings by likely impact, largest first.
4. Finish with the complete rewritten query and the indexes it would benefit from.

Say which assumptions you made about table size and existing indexes. If the query is fine, say so and stop.
