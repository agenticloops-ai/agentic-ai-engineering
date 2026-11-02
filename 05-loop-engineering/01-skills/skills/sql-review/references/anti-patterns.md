# SQL Anti-Patterns

| Code | Pattern | Why it hurts | Fix |
|------|---------|--------------|-----|
| SQL-01 | `SELECT *` | Reads unused columns and breaks index-only scans | Name the columns |
| SQL-02 | A function on an indexed column (`YEAR(created_at) = 2025`) | The index cannot be used | Compare a range: `created_at >= '2025-01-01' AND created_at < '2026-01-01'` |
| SQL-03 | `IN (SELECT ...)` on a large set | Often planned worse than a join | Use `EXISTS` or `JOIN` |
| SQL-04 | Leading wildcard (`LIKE '%term'`) | Forces a full scan | Use full-text search or a trigram index |
| SQL-05 | `OR` across different columns | Often prevents index use | Split into `UNION ALL` |
| SQL-06 | `OFFSET` for deep pagination | Reads and discards every skipped row | Paginate by key: `WHERE id > :last_id` |
| SQL-07 | No `LIMIT` on an exploratory query | Unbounded result set | Add a `LIMIT` |
