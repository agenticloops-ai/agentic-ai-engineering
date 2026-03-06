# TechFlow API v3 Reference

## Authentication

All API requests require authentication via one of two methods:

### API Key Authentication
Include your API key in the `X-TechFlow-Key` header. API keys are generated from the Admin Dashboard under Settings > API Keys. Each key has configurable scopes (read, write, admin) and an optional expiration date. Keys are 64 characters long and prefixed with `tfk_`.

```
X-TechFlow-Key: tfk_abc123...
```

### OAuth2 Authentication
For user-facing applications, use OAuth2 with the authorization code flow. Register your application at developers.techflow.com to receive a `client_id` and `client_secret`. The authorization endpoint is `https://auth.techflow.com/oauth2/authorize` and the token endpoint is `https://auth.techflow.com/oauth2/token`. Access tokens expire after 1 hour; use the refresh token to obtain new ones without user interaction. Refresh tokens are valid for 30 days.

## Rate Limits

Rate limits are enforced per API key or OAuth2 token:

- **Basic plan**: 100 requests/minute, 5,000 requests/day
- **Pro plan**: 500 requests/minute, 50,000 requests/day
- **Enterprise plan**: 2,000 requests/minute, unlimited daily requests

When rate limited, the API returns HTTP 429 with a `Retry-After` header indicating seconds to wait. Rate limit headers are included in every response: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

## Pagination

List endpoints return paginated results using cursor-based pagination. Each response includes a `next_cursor` field. Pass it as the `cursor` query parameter to fetch the next page. Default page size is 25 items, maximum is 100. Set page size with the `limit` query parameter.

```json
{
  "data": [...],
  "next_cursor": "eyJpZCI6MTAwfQ==",
  "has_more": true
}
```

## Core Endpoints

### Projects
- `GET /v3/projects` — List all projects. Supports `status` filter (active, archived, draft) and `sort` (created_at, updated_at, name).
- `POST /v3/projects` — Create a project. Required fields: `name` (max 128 chars), `workspace_id`. Optional: `description` (max 2000 chars), `template_id`, `visibility` (private, team, public).
- `GET /v3/projects/{id}` — Get project details including member count, task count, and storage usage.
- `PATCH /v3/projects/{id}` — Update project fields. Supports partial updates.
- `DELETE /v3/projects/{id}` — Archive a project (soft delete). Archived projects are retained for 90 days.

### Tasks
- `GET /v3/projects/{id}/tasks` — List tasks. Supports filters: `status` (todo, in_progress, review, done), `assignee_id`, `priority` (low, medium, high, critical), `due_before`, `due_after`, `label`.
- `POST /v3/projects/{id}/tasks` — Create a task. Required: `title` (max 256 chars). Optional: `description` (Markdown, max 10000 chars), `assignee_id`, `priority`, `due_date`, `labels[]`, `parent_task_id`.
- `GET /v3/tasks/{id}` — Get task with full details, comments, and activity history.
- `PATCH /v3/tasks/{id}` — Update task. All fields optional.

### Users
- `GET /v3/users` — List workspace members. Supports `role` filter (owner, admin, member, guest).
- `GET /v3/users/{id}` — Get user profile including role, teams, and activity stats.
- `POST /v3/users/invite` — Invite a user by email. Required: `email`, `role`. Optional: `team_ids[]`.

### Webhooks
- `POST /v3/webhooks` — Register a webhook. Required: `url` (HTTPS only), `events[]`. Supported events: `project.created`, `project.updated`, `task.created`, `task.updated`, `task.completed`, `member.added`, `member.removed`.
- `GET /v3/webhooks` — List registered webhooks with delivery stats.
- `DELETE /v3/webhooks/{id}` — Remove a webhook registration.

Webhook payloads are signed with HMAC-SHA256 using your webhook secret. Verify the `X-TechFlow-Signature` header before processing. Failed deliveries are retried 3 times with exponential backoff (1 min, 5 min, 30 min).

## Error Codes

| Code | Meaning | Common Cause |
|------|---------|-------------|
| 400 | Bad Request | Invalid JSON or missing required fields |
| 401 | Unauthorized | Missing or invalid API key / expired token |
| 403 | Forbidden | Insufficient scope or permissions |
| 404 | Not Found | Resource doesn't exist or was archived |
| 409 | Conflict | Duplicate resource (e.g., project name) |
| 422 | Unprocessable | Valid JSON but semantic errors (e.g., invalid date) |
| 429 | Rate Limited | Too many requests — check Retry-After header |
| 500 | Server Error | Internal error — contact support with request ID |

All error responses include a `request_id` for support tracing and a human-readable `message` field.

## Versioning

The API uses URL-based versioning (`/v3/`). Breaking changes are only introduced in new major versions. Deprecated endpoints return a `Sunset` header with the removal date. The current version (v3) was released January 2024. Version v2 will be sunset on June 2025.
