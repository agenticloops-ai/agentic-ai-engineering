# TechFlow Deployment Guide

## CI/CD Pipeline

TechFlow uses GitHub Actions for continuous integration and deployment. Every push to a feature branch triggers the CI pipeline; merges to `main` trigger deployment to staging; production deploys require manual approval.

### Pipeline Stages

1. **Lint & Format** — Runs ruff and black on all Python services. Fails the build if any violations are found. ESLint for Node.js services.
2. **Unit Tests** — Runs pytest with coverage reporting. Minimum coverage threshold: 80%. Tests run in parallel across 4 workers.
3. **Integration Tests** — Spins up PostgreSQL, Redis, and Kafka in Docker containers. Runs end-to-end API tests against the full service stack. Timeout: 15 minutes.
4. **Security Scan** — Runs Snyk for dependency vulnerabilities and Bandit for Python security issues. Critical vulnerabilities block the build.
5. **Build & Push** — Builds Docker images and pushes to AWS ECR. Images are tagged with the git SHA and `latest` for the main branch.
6. **Deploy to Staging** — Automatic for `main` branch. Updates ECS task definitions and triggers a rolling deployment.
7. **Deploy to Production** — Requires manual approval from a team lead. Uses blue-green deployment strategy.

### Build Times
- Average CI pipeline: 8 minutes
- Average deployment (staging): 4 minutes
- Average deployment (production): 6 minutes (including blue-green switch)

## Environment Configuration

### Environment Variables
Each service reads configuration from environment variables, managed via AWS Systems Manager Parameter Store. Environment-specific values (staging vs production) are stored under separate paths:

```
/techflow/staging/auth-service/DATABASE_URL
/techflow/production/auth-service/DATABASE_URL
```

### Required Environment Variables (All Services)
- `ENVIRONMENT` — `staging` or `production`
- `LOG_LEVEL` — `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`)
- `KAFKA_BOOTSTRAP_SERVERS` — Comma-separated Kafka broker addresses
- `REDIS_URL` — Redis connection string with authentication
- `SENTRY_DSN` — Error tracking endpoint

### Service-Specific Variables
- **Auth Service**: `DATABASE_URL`, `JWT_SECRET_KEY`, `OAUTH2_CLIENT_IDS`, `SESSION_TTL_SECONDS`
- **Project Service**: `DATABASE_URL`, `READ_REPLICA_URL`, `PGBOUNCER_MAX_CONNECTIONS`
- **Notification Service**: `SES_REGION`, `FCM_CREDENTIALS`, `WEBHOOK_SIGNING_SECRET`
- **File Service**: `S3_BUCKET`, `CLOUDFRONT_DOMAIN`, `MAX_UPLOAD_SIZE_MB`, `CLAMAV_HOST`

## Database Migrations

Database migrations are managed with Alembic (Python services) and are applied automatically during deployment.

### Migration Process
1. Developer creates migration: `alembic revision --autogenerate -m "add_labels_table"`
2. Migration is reviewed in PR (all migrations must be backward-compatible)
3. On deploy, the ECS task's init container runs `alembic upgrade head` before the service starts
4. If migration fails, the deployment is rolled back automatically

### Migration Rules
- **Always backward-compatible**: The old code must work with the new schema during rolling deploys
- **No dropping columns in the same release**: First release removes code references, second release drops the column
- **Add indexes concurrently**: Use `CREATE INDEX CONCURRENTLY` to avoid locking tables
- **Large data migrations**: Run as background jobs, not in migration scripts (to avoid deploy timeouts)
- **Migration timeout**: 60 seconds per migration. Migrations exceeding this are killed and the deploy fails.

## Rollback Procedures

### Automatic Rollback
ECS monitors container health checks during deployment. If the new containers fail health checks within 5 minutes, the deployment automatically rolls back to the previous task definition. Health check endpoint: `GET /health` must return 200 within 3 seconds.

### Manual Rollback
To manually roll back a production deployment:

1. Go to AWS Console > ECS > Cluster > Service
2. Click "Update service"
3. Select the previous task definition revision
4. Check "Force new deployment"
5. Click "Update"

Or via CLI:
```bash
aws ecs update-service --cluster techflow-prod \
  --service api-gateway \
  --task-definition api-gateway:42 \
  --force-new-deployment
```

Rollbacks typically complete within 3-4 minutes. The previous Docker image is always available in ECR (images are retained for 90 days).

### Database Rollback
If a database migration needs to be reversed:
```bash
alembic downgrade -1  # Roll back one revision
```
This only works if the migration has a proper `downgrade()` function. All migrations must include downgrade steps.

## Health Checks

Every service exposes two health endpoints:

- `GET /health` — Basic liveness check. Returns 200 if the process is running. Used by ECS for container health monitoring.
- `GET /health/ready` — Readiness check. Verifies database connectivity, Redis connectivity, and Kafka consumer group status. Returns 200 only when the service can handle requests. Used by the load balancer to route traffic.

Health check intervals: ECS checks `/health` every 30 seconds. The load balancer checks `/health/ready` every 10 seconds. A service is removed from the load balancer after 3 consecutive failed readiness checks.

## Scaling Policies

### Auto-Scaling Configuration
Each service has independent auto-scaling rules:

| Service | Min | Max | Scale-Up Trigger | Scale-Down Trigger |
|---------|-----|-----|-----------------|-------------------|
| API Gateway | 4 | 12 | CPU > 60% for 3 min | CPU < 30% for 10 min |
| Auth Service | 3 | 8 | CPU > 70% for 3 min | CPU < 30% for 10 min |
| Project Service | 4 | 16 | CPU > 65% for 3 min | CPU < 25% for 15 min |
| Notification Service | 2 | 6 | Queue depth > 10,000 | Queue depth < 1,000 |
| Search Service | 2 | 8 | CPU > 70% for 3 min | CPU < 30% for 10 min |
| File Service | 2 | 6 | CPU > 70% for 5 min | CPU < 30% for 15 min |

### Peak Hours
Traffic peaks between 9:00-11:00 AM and 2:00-4:00 PM EST on weekdays. Pre-scaling is configured to bring services to 75% of max capacity at 8:45 AM EST to avoid cold-start latency.

## Monitoring

### Prometheus & Grafana
All services expose metrics on `/metrics` endpoint (Prometheus format). Key dashboards:
- **Service Health**: Request rate, error rate, latency percentiles (p50, p95, p99)
- **Database**: Query latency, connection pool utilization, replication lag
- **Kafka**: Consumer lag, partition distribution, message throughput
- **Business Metrics**: Active users, tasks created, API calls by endpoint

### Alerting Rules
- **P1 (page immediately)**: Error rate > 5% for 2 minutes, service completely down, database replication lag > 30 seconds
- **P2 (Slack alert)**: Error rate > 1% for 5 minutes, p95 latency > 500ms, disk usage > 80%
- **P3 (ticket)**: p95 latency > 200ms, memory usage > 70%, certificate expiring within 14 days

### Incident Response
1. **Detect**: Automated alerts via PagerDuty (P1) or Slack (P2/P3)
2. **Triage**: On-call engineer assesses severity and impact within 5 minutes
3. **Communicate**: Status page updated at status.techflow.com within 10 minutes for P1 incidents
4. **Resolve**: Fix applied, monitoring confirms recovery
5. **Post-mortem**: Written within 48 hours for all P1 and P2 incidents. Includes timeline, root cause, action items.
