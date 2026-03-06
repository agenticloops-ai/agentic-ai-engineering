# TechFlow System Architecture

## Overview

TechFlow uses a microservices architecture deployed on AWS. The system handles approximately 50,000 concurrent users during peak hours with an average API response time of 45ms at the 95th percentile.

## Service Map

### API Gateway (Kong)
The API Gateway is the single entry point for all client requests. It handles SSL termination, request routing, rate limiting, and API key validation. The gateway runs on 4 instances behind an AWS Application Load Balancer with auto-scaling between 4-12 instances based on CPU utilization (target: 60%).

### Auth Service
Handles authentication and authorization. Manages user sessions, API key validation, OAuth2 flows, and permission checks. Built with Python (FastAPI) and uses PostgreSQL for user data and Redis for session caching. Session tokens are JWT-based with 1-hour expiry. The service validates permissions using a role-based access control (RBAC) model with four roles: owner, admin, member, and guest.

### Project Service
Core business logic for projects, tasks, labels, and workflows. This is the largest service (~40,000 lines) and handles all CRUD operations for project management. Built with Python (Django) and PostgreSQL. Uses database connection pooling (PgBouncer, max 200 connections) to handle concurrent requests efficiently. Complex queries (reporting, analytics) are routed to a read replica to avoid impacting write performance.

### Notification Service
Manages all outbound notifications: email (via AWS SES), in-app notifications (via WebSocket), push notifications (via Firebase Cloud Messaging), and webhook deliveries. Built with Node.js and uses a Redis-backed queue to decouple notification processing from the main request flow. Failed webhook deliveries are retried with exponential backoff. The service processes approximately 2 million notifications per day.

### Search Service
Powers full-text search across projects, tasks, and comments. Built on Elasticsearch with custom analyzers for code snippet search. Indexes are updated asynchronously via Kafka events. Search results are ranked using a combination of text relevance, recency, and user activity signals. The index is rebuilt nightly to clean up stale entries.

### File Service
Handles file uploads, storage, and retrieval. Files are stored in AWS S3 with CloudFront CDN for delivery. Supports files up to 100MB. Generates thumbnails for images and preview renders for documents. Virus scanning is performed asynchronously via ClamAV before files are made available. Storage quotas are enforced per workspace: 5GB (Basic), 50GB (Pro), unlimited (Enterprise).

## Database Architecture

### PostgreSQL (Primary Database)
- **Version**: PostgreSQL 15 on AWS RDS
- **Configuration**: Multi-AZ deployment with automatic failover
- **Primary instance**: db.r6g.2xlarge (8 vCPU, 64GB RAM)
- **Read replica**: Used for analytics queries and reporting dashboards
- **Backup**: Automated daily snapshots retained for 30 days, point-in-time recovery enabled
- **Tables**: 47 tables across 6 schemas (public, auth, projects, billing, audit, analytics)

### Redis (Caching & Sessions)
- **Version**: Redis 7 on AWS ElastiCache
- **Cluster**: 3-node cluster with automatic failover
- **Usage**: Session storage (TTL: 1 hour), API response caching (TTL: 5 minutes), rate limit counters, real-time presence tracking
- **Memory**: 32GB per node, eviction policy: volatile-lru

### Elasticsearch (Search)
- **Version**: OpenSearch 2.11 on AWS
- **Cluster**: 3 data nodes + 2 dedicated master nodes
- **Indexes**: projects, tasks, comments, files (metadata only)
- **Refresh interval**: 1 second (near real-time search)

## Event-Driven Architecture

Services communicate asynchronously via Apache Kafka. This decouples services and enables reliable event processing even during partial outages.

### Kafka Configuration
- **Cluster**: 3 brokers on AWS MSK
- **Replication factor**: 3 (every message is stored on all brokers)
- **Retention**: 7 days for all topics

### Key Topics
- `project.events` — Project created, updated, archived, restored. Consumed by: Search Service, Notification Service, Analytics.
- `task.events` — Task created, updated, status changed, assigned, commented. Consumed by: Search Service, Notification Service, Analytics. Highest volume topic (~500K events/day).
- `user.events` — User registered, profile updated, role changed, deactivated. Consumed by: Auth Service (cache invalidation), Notification Service.
- `file.events` — File uploaded, scanned, deleted. Consumed by: File Service (thumbnail generation), Search Service (metadata indexing).
- `billing.events` — Subscription created, upgraded, downgraded, payment failed. Consumed by: Notification Service, Auth Service (feature flag updates).

### Event Schema
All events follow a standard envelope format:
```json
{
  "event_id": "evt_abc123",
  "event_type": "task.updated",
  "timestamp": "2024-01-15T10:30:00Z",
  "actor_id": "usr_xyz789",
  "workspace_id": "ws_def456",
  "payload": { ... }
}
```

## Deployment Topology

All services run on AWS ECS (Fargate) with the following configuration:
- **Region**: us-east-1 (primary), eu-west-1 (disaster recovery)
- **Networking**: VPC with public subnets (load balancers), private subnets (services, databases)
- **DNS**: Route 53 with health-check-based failover
- **CDN**: CloudFront for static assets and file downloads
- **Secrets**: AWS Secrets Manager for API keys, database credentials, and encryption keys
