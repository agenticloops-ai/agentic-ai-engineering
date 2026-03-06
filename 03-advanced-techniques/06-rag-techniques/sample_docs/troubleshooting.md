# TechFlow Troubleshooting Guide

## API Returns 429 (Rate Limited)

### Symptoms
API requests return HTTP 429 with a message like "Rate limit exceeded. Retry after 30 seconds." This occurs when your application exceeds the allowed request rate for your plan tier.

### Diagnosis
1. Check the `X-RateLimit-Remaining` header in your API responses. If it's consistently at 0, you're hitting the limit.
2. Review your request patterns — are you making unnecessary polling calls? Are you retrying failed requests too aggressively?
3. Check if multiple services or applications share the same API key.

### Solutions
- **Implement exponential backoff**: When you receive a 429, wait the number of seconds in the `Retry-After` header, then double the wait time on each subsequent retry (max 5 retries).
- **Cache API responses**: If you're fetching the same data repeatedly, cache responses locally for 30-60 seconds.
- **Use webhooks instead of polling**: Instead of polling `GET /v3/tasks` every 10 seconds, register a webhook for `task.updated` events.
- **Request a rate limit increase**: Pro and Enterprise plans can request custom rate limits by contacting support@techflow.com.
- **Use bulk endpoints**: Instead of fetching tasks one by one, use `GET /v3/projects/{id}/tasks?limit=100` to batch requests.

## Webhooks Not Firing

### Symptoms
Registered webhooks are not delivering events to your endpoint. The webhook dashboard shows no recent deliveries, or deliveries are showing as failed.

### Diagnosis
1. Check the webhook dashboard at Settings > Webhooks. Click on a specific webhook to see delivery history and failure reasons.
2. Verify your endpoint is accessible from the public internet (webhooks cannot be delivered to `localhost` or private IPs).
3. Check that your endpoint returns a 2xx status code within 10 seconds. Timeouts and non-2xx responses are treated as failures.
4. Verify the webhook is registered for the correct events. Common mistake: registering for `task.created` but expecting `task.updated` events.

### Solutions
- **Verify HTTPS**: Webhooks require HTTPS endpoints with valid SSL certificates. Self-signed certificates are rejected.
- **Check firewall rules**: Whitelist TechFlow's webhook IPs: `52.20.118.0/24` and `52.45.205.0/24`.
- **Validate signature verification**: If your endpoint rejects requests, check that you're using the correct webhook secret for HMAC-SHA256 verification. The secret is shown once during webhook registration.
- **Check retry status**: Failed deliveries are retried 3 times (at 1 min, 5 min, and 30 min). After 3 failures, the webhook is marked as "failing" and delivery pauses. Re-enable it from the dashboard after fixing your endpoint.
- **Test with the webhook tester**: Use Settings > Webhooks > Test to send a sample event to your endpoint and see the response in real-time.

## Slow Query Performance

### Symptoms
API responses are slow (>500ms) for list endpoints like `GET /v3/projects/{id}/tasks` or search queries. The slowness may be intermittent, worsening during peak hours.

### Diagnosis
1. Check if the slowness is on specific endpoints or system-wide. System-wide slowness suggests a database issue; endpoint-specific slowness suggests a missing index.
2. Review query parameters — are you fetching large result sets without pagination? Default limit is 25, but setting `limit=1000` can cause timeouts.
3. Check if you're using filters. Unfiltered list requests on large projects (10,000+ tasks) are inherently slower.

### Solutions
- **Use pagination**: Always set a reasonable `limit` (25-100) and use cursor-based pagination to iterate through results.
- **Add filters**: Use `status`, `assignee_id`, or `due_before`/`due_after` filters to narrow results. Filtered queries use database indexes and are 10-50x faster than unfiltered scans.
- **Avoid deep pagination**: Fetching page 500 of results is slow because the database must skip 12,500 rows. If you need to process all tasks, use the `GET /v3/projects/{id}/tasks/export` endpoint for bulk data access.
- **Use the search endpoint**: For text-based lookups, `GET /v3/search?q=keyword` uses Elasticsearch and is faster than scanning with `GET /v3/tasks?title=keyword`.
- **Cache frequently accessed data**: If you display a project dashboard, cache the task counts and summaries for 30-60 seconds instead of fetching live data on every page load.
- **Contact support for indexing**: If specific queries are consistently slow, contact support with the request ID. Our team can add database indexes for common query patterns.

## Authentication Failures

### Symptoms
API requests return 401 Unauthorized or 403 Forbidden errors. Users report being logged out unexpectedly or unable to access resources they should have permission for.

### Diagnosis
1. **401 errors**: The API key is missing, malformed, or expired. Check the `X-TechFlow-Key` header format.
2. **403 errors**: The API key is valid but lacks the required scope. Check key scopes in Admin Dashboard > API Keys.
3. For OAuth2 tokens: check if the access token has expired (1-hour TTL). Decode the JWT at jwt.io to verify the `exp` claim.
4. Check if the user's role has changed recently. Permission changes take effect immediately but cached sessions may retain old permissions for up to 5 minutes.

### Solutions
- **Refresh expired tokens**: Implement automatic token refresh in your client. When you receive a 401, use the refresh token to obtain a new access token before retrying.
  ```
  POST /oauth2/token
  grant_type=refresh_token
  refresh_token=<your_refresh_token>
  client_id=<your_client_id>
  ```
- **Check API key scopes**: Each key has specific scopes. A key with only `read` scope cannot create or update resources. Generate a new key with the required scopes.
- **Verify key is active**: Keys can be deactivated by workspace admins. Check Settings > API Keys for status.
- **Handle role changes**: If a user's role changes from admin to member, some endpoints become inaccessible. Your application should handle 403 errors gracefully and inform the user.
- **Check account suspension**: If the workspace's billing has failed, all API access is suspended. Check billing status at Settings > Billing.

## Data Sync Delays

### Symptoms
Changes made via the API or UI don't appear immediately in search results, reports, or webhook deliveries. For example, a task is created but doesn't show up in search for 5-10 seconds.

### Diagnosis
This is usually expected behavior due to TechFlow's eventual consistency model. Different data paths have different latency:

| Operation | Expected Delay | Reason |
|-----------|---------------|--------|
| API response reflects change | Immediate | Direct database read |
| Search index updated | 1-3 seconds | Kafka event → Elasticsearch |
| Analytics dashboard updated | 5-10 minutes | Batch aggregation job |
| Webhook delivered | 1-30 seconds | Queue processing + delivery |
| Cross-service data (e.g., user name in task) | Up to 5 minutes | Cache TTL in consuming service |

### Solutions
- **Understand consistency boundaries**: API reads are strongly consistent (you always see your own writes). Search and analytics are eventually consistent.
- **Use the API for real-time reads**: If you need the latest state immediately after an update, read from the API directly rather than relying on search or cached data.
- **Check Kafka consumer lag**: If search delays exceed 10 seconds consistently, there may be consumer lag. Check the Search Service health dashboard or contact support.
- **Webhook ordering**: Webhooks are delivered in order per resource, but may arrive out of order across different resources. Use the `event_id` and `timestamp` fields to reconcile ordering in your system.
- **Force cache refresh**: For the Auth Service specifically, you can force a permission cache refresh by calling `POST /v3/auth/refresh-cache` with admin credentials. This is useful after bulk role changes.

## File Upload Failures

### Symptoms
File uploads fail with various error messages, or uploaded files are not accessible after upload completes.

### Diagnosis
1. Check file size — maximum is 100MB per file.
2. Check file type — executable files (.exe, .bat, .sh, .ps1) are blocked for security.
3. If the upload succeeds but the file is not accessible, the virus scan may have quarantined it. Check the file status via `GET /v3/files/{id}` — status will be `quarantined` if flagged.

### Solutions
- **Compress large files**: If your file exceeds 100MB, compress it (ZIP, GZIP) before uploading.
- **Use multipart upload**: For files over 10MB, use the multipart upload endpoint `POST /v3/files/multipart` which uploads in 5MB chunks and supports resume on failure.
- **Check storage quota**: Verify workspace storage hasn't exceeded plan limits (5GB Basic, 50GB Pro, unlimited Enterprise). Check usage at Settings > Storage.
- **Wait for virus scan**: After upload, files transition through states: `uploading` → `scanning` → `available` (or `quarantined`). The scan typically takes 5-15 seconds. Poll `GET /v3/files/{id}` or listen for the `file.scanned` webhook event.
