# Kernlog SaaS — Implementation Task Plan

## Project Description
Kernlog is a multi-tenant, real-time infrastructure monitoring SaaS. Users create an organization, generate agent API keys, install a Python agent on hosts, and view live metrics/logs/alerts in a Next.js dashboard. Data isolation by `tenant_id` is mandatory in every storage and query path. Stack is fully free-tier oriented: Neon PostgreSQL, Upstash QStash, Upstash Redis, Render, and Vercel. No Docker is used for local development or runtime.

## Scope and Build Order
- Repo 1 first: `kernlog-backend` (FastAPI API + WebSocket + QStash ingestion + alert engine + agent package).
- Repo 2 second: `kernlog-frontend` (Next.js dashboard and onboarding UI only after backend is stable and deployed).
- Alerting is threshold-based only. No AI/ML.

---

## Phase 0 — Local Development Setup (Backend First)
> Deliver a runnable backend workspace with native process workflow and cloud-managed dependencies.
> Comment: Phase 0 is completed in this repository.

### TASK-001: Create backend repository skeleton [INFRA] [M] [COMPLETED]
- Create directories: `app/`, `alert_engine/`, `agent/`, `scripts/`, `migrations/`.
- Add base files: `requirements.txt`, `agent/requirements.txt`, `.env.example`, `Makefile`, `Procfile`, `README.md`.
- Add package markers and minimal module files: `app/__init__.py`, `app/main.py`, `alert_engine/__init__.py`, `alert_engine/main.py`.
- Document Python version target as 3.11 in README.
- Keep structure backend-only; do not create frontend repo yet.

Test cases:
- `tree -L 2` shows required directories/files.
- `python -m py_compile app/main.py alert_engine/main.py` passes.
- README includes setup steps and backend-first note.

### TASK-002: Define backend environment contract [DEVOPS] [S] [COMPLETED]
- Add all required vars to `.env.example`: `NEON_DATABASE_URL`, `UPSTASH_QSTASH_URL`, `UPSTASH_QSTASH_TOKEN`, `UPSTASH_QSTASH_CURRENT_SIGNING_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `JWT_SECRET`, `JWT_REFRESH_SECRET`, `PORT`, `ENVIRONMENT`, `CORS_ORIGIN`.
- Add inline comments for each variable purpose and format.
- Add startup validation utility in `app/config.py`.
- Fail-fast app boot if required vars are missing.

Test cases:
- Start app with missing `JWT_SECRET` fails with clear error.
- Start app with all vars present succeeds.
- `.env.example` contains every required key exactly once.

### TASK-003: Add local process commands [DEVOPS] [S] [COMPLETED]
- Add Makefile commands: `backend`, `alerts`, `migrate`, `seed`, `topics`.
- Configure `Procfile` with `web` and `worker` process definitions.
- Ensure commands use project-relative module paths.
- Document `honcho start` usage in README.

Test cases:
- `make -n backend alerts migrate seed topics` resolves commands.
- `honcho start` recognizes both `web` and `worker` entries.

---

## Phase 1 — Database and Migration Foundation
> Deliver Neon schemas/tables/indexes and idempotent migration workflow.

### TASK-004: Configure Alembic for Neon and schema search path [BACKEND] [M] [COMPLETED]
- Initialize Alembic in repo.
- Set `sqlalchemy.url` via `NEON_DATABASE_URL`.
- Configure `search_path=app,metrics,public` in Alembic runtime settings.
- Add migration runner script `scripts/migrate.py` calling `alembic upgrade head`.

Test cases:
- `python scripts/migrate.py` runs against Neon without schema resolution errors.
- `alembic current` outputs expected revision.

### TASK-005: Create initial SQL migration for all schemas/tables/indexes [BACKEND] [L] [COMPLETED]
- Add `migrations/001_initial.sql` with `CREATE SCHEMA IF NOT EXISTS app;` and `metrics`.
- Create relational tables in `app`: `organizations`, `users`, `refresh_tokens`, `agent_keys`, `hosts`, `alert_rules`, `alerts`.
- Create time-series/log tables in `metrics`: `metrics`, `logs`.
- Create indexes: `idx_metrics_lookup`, `idx_logs_lookup`.
- Ensure all objects use `IF NOT EXISTS` where applicable.

Test cases:
- First migration run creates all objects.
- Second migration run is idempotent with no fatal DDL errors.
- `SELECT * FROM information_schema.tables` shows tables in correct schemas.

### TASK-006: Implement seed script for dev tenant/user/key [BACKEND] [M] [COMPLETED]
- Implement `scripts/seed.py` for org `test-org` and owner `dev@kernlog.io`.
- Hash password `devpassword` with bcrypt.
- Generate agent raw key `kl_live_*`, store SHA-256 hash + prefix.
- Make script idempotent by checking existing slug/email/key prefix.

Test cases:
- First run inserts org, user, key.
- Second run does not duplicate records.
- Login with seeded user works after auth phase implementation.

---

## Phase 2 — Authentication Service
> Deliver JWT auth and refresh-token rotation with tenant-scoped claims.

### TASK-007: Implement auth models and token utilities [AUTH] [M] [COMPLETED]
- Add Pydantic schemas for register/login/refresh/logout payloads.
- Implement JWT creation helpers with claims: `user_id`, `tenant_id`, `email`, `role`.
- Access token expiry: 15 minutes; refresh: 7 days.
- Hash refresh token with SHA-256 before DB persistence.

Test cases:
- Generated access token includes required claims.
- Expired token fails validation.
- Refresh token hash differs from raw token.

### TASK-008: Build auth endpoints `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` [AUTH] [L] [COMPLETED]
- `POST /auth/register`: create org + owner user, return access+refresh tokens.
- `POST /auth/login`: validate email/password via bcrypt, issue new tokens.
- `POST /auth/refresh`: rotate refresh token, revoke old token, issue new pair.
- `POST /auth/logout`: revoke current refresh token.
- Keep tenant context derived from user record, never request payload.

Test cases:
- Register returns tokens and created tenant.
- Login rejects wrong password with 401.
- Refresh invalidates previous refresh token.
- Logout prevents further refresh with same token.

### TASK-009: Add `require_auth` dependency and route protection [AUTH] [M] [COMPLETED]
- Implement `require_auth` dependency in `app/deps/auth.py`.
- Validate bearer token signature, expiration, and claims.
- Return normalized auth context `{user_id, tenant_id, role}`.
- Apply dependency to protected routers.

Test cases:
- Protected route without token returns 401.
- Token from tenant A cannot access tenant B data.
- Malformed JWT returns deterministic auth error.

### Phase 1 & 2 Implementation Approach (Completed on May 29, 2026)
- Used SQLAlchemy + Alembic with runtime env loading from `NEON_DATABASE_URL`, and enforced `search_path=app,metrics,public` both in Alembic runtime and app DB engine.
- Kept schema provisioning idempotent via `IF NOT EXISTS` DDL in `migrations/001_initial.sql`, and wired Alembic revision to execute this SQL file directly for predictable Neon-compatible setup.
- Implemented `scripts/migrate.py` as a real migration runner (`alembic upgrade head`) and replaced seed placeholder with an idempotent seeder for `test-org`, `dev@kernlog.io`, and one agent key.
- Implemented auth using short-lived access JWT (15 min) + refresh JWT (7 days), with required claims (`user_id`, `tenant_id`, `email`, `role`) and token-type separation.
- Implemented refresh-token rotation and revocation using SHA-256 token hashing in `app.refresh_tokens` so raw refresh tokens are never stored.
- Added tenant-safe auth flow endpoints (`/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`) where tenant context is always derived from DB/user identity, not trusted from incoming payload.
- Added `require_auth` dependency for bearer validation and normalized auth context output, and attached it to a protected route (`GET /me`) to enforce route-level protection.

---

## Phase 3 — Organization and Agent Key Management
> Deliver tenant admin endpoints and secure agent key lifecycle.

### TASK-010: Implement org profile endpoint `GET /org` [BACKEND] [S] [COMPLETED]
- Add `GET /org` protected route.
- Query `app.organizations` by `tenant_id` from JWT claims.
- Return plan, host limits, retention, created_at.
- Exclude unrelated tenant records.

Test cases:
- Authenticated user sees only own org data.
- Unknown tenant claim returns 404/401 safely.

### TASK-011: Implement agent key CRUD endpoints [BACKEND] [M] [COMPLETED]
- `GET /org/agent-keys`: return key id/prefix/label/created/last_used/revoked.
- `POST /org/agent-keys`: generate raw key format `kl_live_{32chars}`, store hash + prefix, return raw once.
- `DELETE /org/agent-keys/{id}`: set `revoked_at`.
- Never return or store raw key after creation response.

Test cases:
- Created key is shown once and cannot be retrieved later.
- Revoked key remains listed with `revoked_at` set.
- Cross-tenant key deletion attempt fails.

### TASK-012: Add Redis-backed key hash to tenant cache resolver [BACKEND] [M] [COMPLETED]
- Implement key resolution service: hash raw key via SHA-256.
- Redis lookup first with TTL 300 seconds.
- On cache miss query `app.agent_keys` (non-revoked), then populate cache.
- Namespace cache key as `kernlog:keys:{key_hash}`.

Test cases:
- First lookup hits Postgres then writes Redis.
- Second lookup hits Redis only.
- Revoked key resolution returns unauthorized.

### Phase 3 Implementation Approach (Completed on May 29, 2026)
- Added a dedicated organization router and protected all Phase 3 endpoints using `require_auth` so tenant context always comes from JWT claims.
- Implemented `GET /org` with tenant-scoped lookup on `app.organizations` and safe `404` behavior when claim/org mismatch exists.
- Implemented agent key lifecycle:
- `GET /org/agent-keys` lists tenant keys only with metadata (`id`, `key_prefix`, `label`, `created_at`, `last_used_at`, `revoked_at`).
- `POST /org/agent-keys` generates `kl_live_{32hex}` raw keys, stores only SHA-256 hash + prefix, and returns the raw key once in the creation response.
- `DELETE /org/agent-keys/{id}` performs tenant-scoped soft revoke via `revoked_at`.
- Added Redis REST backed resolver service in `app/services/key_resolver.py`:
- Hash raw key to SHA-256.
- Read-through cache key format `kernlog:keys:{key_hash}` with 300s TTL.
- On miss, query non-revoked `app.agent_keys`, then populate Redis cache.

### Postman Testing Collection (Current APIs)
- Added importable collection: `postman/kernlog-backend.postman_collection.json`.
- Added local environment file: `postman/kernlog-local.postman_environment.json`.
- Included all currently implemented APIs:
- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /me`
- `GET /org`
- `GET /org/agent-keys`
- `POST /org/agent-keys`
- `DELETE /org/agent-keys/{id}`

### Future Step: Keep Postman JSON Updated
- Whenever a new API endpoint is added/changed, update `postman/kernlog-backend.postman_collection.json` in the same PR.
- Keep `postman/kernlog-local.postman_environment.json` in sync with new variables used by collection requests.
- Add request body examples for all non-GET routes and required headers (especially `Authorization: Bearer {{accessToken}}`).
- Add/update collection variables for any new dynamic values (`hostId`, `alertRuleId`, etc.).
- Ensure endpoint grouping remains phase-aligned (`Auth`, `Organization`, `Agent`, `Alerts`, etc.) so testing flow stays predictable.
- Validate import once in Postman before merging to avoid broken JSON/check-in mistakes.

---

## Phase 4 — Monitoring Agent Package
> Deliver installable Python agent with metrics/log shipping and graceful runtime behavior.

### TASK-013: Scaffold `kernlog-agent` package structure [AGENT] [M] [COMPLETED]
- Create `agent/kernlog_agent/` with `collectors/`, `producers/`, `config.py`, `main.py`.
- Add packaging metadata (`pyproject.toml` or `setup.py`) for `pip install kernlog-agent`.
- Expose CLI entrypoint: `kernlog-agent`.
- Split backend vs agent dependencies.

Test cases:
- `pip install -e agent/` installs package.
- `kernlog-agent --help` prints CLI usage.

### TASK-014: Build config loader for `/etc/kernlog/config.yaml` [AGENT] [M] [COMPLETED]
- Parse fields: `agent_key`, Upstash QStash creds/url, `host_id`, `host_label`, `log_file_paths`, `collection_interval_seconds`.
- Default `host_id` to hostname and interval to 15.
- Validate required fields and readable log paths.
- Add clear startup error messages.

Test cases:
- Missing `agent_key` blocks startup with readable error.
- Minimal config uses defaults correctly.
- Invalid YAML fails gracefully.

### TASK-015: Implement agent registration client [AGENT] [M] [COMPLETED]
- On startup call `POST /api/v1/agent/register`.
- Send `agent_key` header and metadata body `{host_id,label,os,arch,agent_version}`.
- Cache returned `tenant_id` and normalized `host_id` for message payloads.
- Retry transient failures with bounded backoff.

Test cases:
- Valid key returns `registered=true` and tenant id.
- Revoked/invalid key fails and prevents run loop.
- Network timeout retries then exits after configured limit.

### TASK-016: Implement system metrics collector (no Docker metrics) [AGENT] [M] [COMPLETED]
- Collect CPU, memory, disk `/`, and network counters via `psutil`.
- Build topic payloads with top-level `tenant_id` and `host_id`.
- Emit to `metrics.system` every configured interval.
- Add monotonic timestamp field.

Test cases:
- Collector emits expected metric names and numeric values.
- Interval pacing remains stable across cycles.

### TASK-017: Implement log tailer using `watchdog` [AGENT] [L] [COMPLETED]
- Watch configured files and append new lines only.
- Produce each new line to topic `logs.app` with file path and timestamp.
- Include top-level `tenant_id` and `host_id` in each message.
- Handle file rotation/reopen events.

Test cases:
- Appended log line appears as single produced event.
- File rotation continues ingestion without duplicate flood.

### TASK-018: Implement Upstash QStash producer wrapper with retries [AGENT] [M] [COMPLETED]
- Use `QStash` REST-based producer client.
- Configure from `UPSTASH_QSTASH_URL`, `UPSTASH_QSTASH_TOKEN`, `UPSTASH_QSTASH_CURRENT_SIGNING_KEY`.
- Add exponential backoff for HTTP errors.
- Return structured success/failure stats for observability.

Test cases:
- Successful publish returns ack metadata.
- Simulated 5xx triggers retry behavior.
- Exhausted retries surfaces non-zero exit path.

### TASK-019: Add graceful shutdown and middleware snippet [AGENT] [M] [COMPLETED]
- Handle SIGTERM/SIGINT in agent main loop.
- Flush producer and close watchers/file descriptors before exit.
- Add standalone `kernlog_middleware.py` for FastAPI apps to push API latency/status to `metrics.api`.
- Document middleware integration snippet.

Test cases:
- SIGTERM exits cleanly without corrupted state.
- Middleware emits endpoint latency payloads with route and status code.

### Phase 4 Implementation Approach (Completed on May 29, 2026)
- Added a proper installable `kernlog-agent` package under `agent/kernlog_agent` with separated collectors/producers modules, package metadata (`setup.py`), and a CLI entrypoint (`kernlog-agent`).
- Implemented strict YAML configuration loading with defaults (`host_id` from hostname, interval default 15), validation for required credentials/keys, and readable error handling via `AgentConfigError`.
- Implemented startup registration client for `POST /api/v1/agent/register` with bounded exponential backoff, invalid-key fail-fast behavior, and normalized tenant/host context capture for subsequent payloads.
- Implemented system metrics collection using `psutil` for CPU, memory, disk root, and network counters with a monotonic timestamp, published to `metrics.system`.
- Implemented watchdog-based log tailing for append-only ingestion to `logs.app`, including rotation/truncation-safe offset reset behavior.
- Added QStash producer wrapper with structured publish result metadata and retry behavior for transient/server errors.
- Added graceful shutdown in the runtime loop (`SIGTERM`/`SIGINT`) to stop loops, close log observers, and close HTTP sessions cleanly.
- Added standalone `agent/kernlog_middleware.py` and documented FastAPI integration snippet in `agent/README.md` for publishing API latency/status metrics to `metrics.api`.

---

## Phase 5 — Agent Registration Endpoint
> Deliver backend registration endpoint secured by agent key auth and rate limits.

### TASK-020: Implement `POST /api/v1/agent/register` with key auth [BACKEND] [M] [COMPLETED]
- Validate `agent_key` header via hash->tenant resolver.
- Upsert into `app.hosts` on `(tenant_id, host_id)` uniqueness.
- Update host metadata (`label`, `os`, `arch`, `agent_version`, `last_seen_at`).
- Return `{tenant_id, host_id, registered: true}`.

Test cases:
- First registration inserts host.
- Re-registration updates metadata without duplicate row.
- Invalid key returns 401.

### TASK-021: Apply endpoint rate limiting (10 req/min per key) [BACKEND] [S] [COMPLETED]
- Add limiter middleware (`slowapi` or equivalent).
- Use raw `agent_key` hash as limiter identity.
- Configure route-specific cap at `10/minute`.
- Return RFC-appropriate 429 response.

Test cases:
- 11th request within minute gets 429.
- Different keys are independently limited.

### Phase 5 Implementation Approach (Completed on May 29, 2026)
- Added a dedicated agent router with `POST /api/v1/agent/register` and included it in FastAPI app wiring.
- Enforced `agent_key` header validation using existing hash-to-tenant key resolver, returning `401` for invalid/revoked keys.
- Implemented host registration as tenant-scoped upsert on `(tenant_id, host_id)` with metadata refresh (`label`, `os`, `arch`, `agent_version`, `last_seen_at`) and response payload `{tenant_id, host_id, registered: true}`.
- Updated `app.agent_keys.last_used_at` on successful registration.
- Added route-specific in-memory rate limiter (`10/minute`) keyed by SHA-256 hash of raw `agent_key` and returned `429` with `Retry-After` header when exceeded.
- Updated Postman collection and local environment with Agent registration request and variables (`agentKey`, `hostId`).
- Comment: Phase 5 backend endpoint and Postman coverage are now in sync and ready for Phase 6 ingestion work.

---

## Phase 6 — QStash Consumer and Ingestion Pipeline
> Deliver background ingestion task in FastAPI process with Redis fanout and Neon persistence.

### TASK-022: Start QStash consumer as FastAPI background task [BACKEND] [L] [COMPLETED]
- Initialize QStash receiver/subscription handler(s) for `metrics.system`, `metrics.api`, `logs.app` at app startup.
- Use Upstash QStash REST credentials from env.
- Run consumer loop in asyncio task group.
- Ensure clean shutdown on app stop.

Test cases:
- App startup launches consumer task.
- App shutdown cancels consumer without unhandled exceptions.

### TASK-023: Implement message parsing/validation and tenant enforcement [BACKEND] [M] [COMPLETED]
- Parse JSON payload and require top-level `tenant_id`, `host_id`.
- Reject malformed messages with structured logs.
- Verify tenant/host consistency before DB writes.
- Keep dead-letter behavior in logs for failed parse events.

Test cases:
- Malformed JSON does not crash consumer loop.
- Missing tenant_id message is rejected and logged.

### TASK-024: Persist metrics and update Redis latest snapshot [BACKEND] [L] [COMPLETED]
- Insert metric points into `metrics.metrics` via asyncpg.
- Update `{tenant_id}:{host_id}:latest` hash with TTL 60s.
- Publish live metric update to `kernlog:{tenant_id}:{host_id}` channel.
- Debounce `app.hosts.last_seen_at` writes (max once/30s) using Redis key `{tenant_id}:{host_id}:lastseen`.

Test cases:
- Consumed metric appears in Neon table.
- Redis latest key is refreshed and expires as expected.
- Pub/sub message appears on tenant+host channel.

### TASK-025: Persist logs, infer severity, and publish live log stream [BACKEND] [M] [COMPLETED]
- Insert log lines into `metrics.logs`.
- Parse severity via regex (`ERROR|WARN|INFO|DEBUG`).
- Publish log event to `kernlog:{tenant_id}:{host_id}:logs`.
- Include fallback severity when pattern absent.

Test cases:
- Log line containing `ERROR` is stored with severity `ERROR`.
- Log stream subscribers receive near-real-time events.

### TASK-026: Commit consumer offsets after successful writes [BACKEND] [M] [COMPLETED]
- Commit offsets only after DB + Redis operations succeed.
- Retry transient failures before abandoning message.
- Keep at-least-once semantics explicit in docs.
- Add idempotency guards where practical.

Test cases:
- Forced DB failure prevents offset commit.
- Restarted consumer reprocesses uncommitted message.

### Phase 6 Implementation Approach (Completed on May 30, 2026)
- Added a dedicated ingestion pipeline in `app/ingestion.py` with:
- Topic-aware parsing/validation for `metrics.system`, `metrics.api`, and `logs.app`.
- Background worker queue (`IngestionWorker`) started in FastAPI lifespan and stopped cleanly on shutdown.
- Retry handling (bounded retries for transient failures) and at-least-once behavior by returning non-2xx on failures.
- Added webhook endpoint `POST /api/v1/ingest/qstash` in `app/routers/ingestion.py`:
- Validates QStash publisher authorization token.
- Parses payload and only acknowledges after successful worker processing.
- Implemented tenant/host enforcement before writes by validating `(tenant_id, host_id)` against `app.hosts`.
- Implemented metrics ingestion:
- Insert into `metrics.metrics`.
- Refresh Redis latest snapshot key `{tenant_id}:{host_id}:latest` with TTL 60s.
- Publish live metric event to Redis channel `kernlog:{tenant_id}:{host_id}`.
- Debounced host heartbeat updates via Redis key `{tenant_id}:{host_id}:lastseen` (30s gate).
- Implemented logs ingestion:
- Insert into `metrics.logs` with severity inference (`ERROR|WARN|INFO|DEBUG`, fallback `INFO`).
- Publish live log event to `kernlog:{tenant_id}:{host_id}:logs`.
- Added idempotency guard for message re-delivery using Redis key `kernlog:ingest:processed:{message_id}`.
- Added migration `20260530_01_add_logs_severity.py` to introduce `metrics.logs.severity`.

### Phase 6 Test Execution Status (May 30, 2026)
- `venv/bin/python -m unittest discover -s tests -p 'test_phase6_ingestion.py'`:
- PASS (4/4) for malformed JSON rejection, required `tenant_id` validation, valid message parse, and severity inference fallback/regex behavior.
- `python3 -m py_compile app/main.py app/ingestion.py app/routers/ingestion.py alembic/versions/20260530_01_add_logs_severity.py`:
- PASS (syntax check successful).
- Integration tests requiring live Neon/Redis/QStash connectivity:
- NOT EXECUTED in this run (no end-to-end cloud dependency exercise in local test step).

---

## Phase 7 — Backend REST API
> Deliver tenant-scoped host, metrics, logs, alerts, and alert-rule endpoints.

### TASK-027: Implement host listing/detail endpoints [BACKEND] [M]
- `GET /api/v1/hosts` returns tenant hosts with `last_seen_at` and Redis latest snapshot.
- `GET /api/v1/hosts/{host_id}` returns single host + latest stats.
- Derive tenant from JWT only.
- Add pagination basics for host lists.

Test cases:
- Host list excludes other tenants.
- Missing host in tenant returns 404.

### TASK-028: Implement metrics query endpoint with PostgreSQL rollups [BACKEND] [L]
- `GET /api/v1/hosts/{host_id}/metrics` with `metric`, `from`, `to`, `interval`.
- Use plain PostgreSQL aggregation with `date_trunc`/bucket strategy (no TimescaleDB).
- Support intervals `1m`, `5m`, `1h`.
- Validate range and cap max query window.

Test cases:
- Valid interval returns ordered points.
- Unsupported interval returns 400.
- Query cannot access other tenant’s host data.

### TASK-029: Implement logs and alerts feed endpoints [BACKEND] [M]
- `GET /api/v1/hosts/{host_id}/logs` with `search`, `severity`, `limit`, pagination cursor.
- `GET /api/v1/alerts` with filters `status`, `host_id`, `limit`.
- Add indexes-aware query plans.
- Enforce tenant filter in all where clauses.

Test cases:
- Severity filter returns only requested level.
- Alert query by host returns tenant-local results only.

### TASK-030: Implement alert rules CRUD endpoints [BACKEND] [M]
- `GET /api/v1/alert-rules`, `POST`, `PUT`, `DELETE`.
- Validate operator enum `gt|lt|gte|lte` and severity enum.
- Allow optional `host_id` null for org-wide rules.
- Emit cache invalidation signal for alert engine on writes.

Test cases:
- Creating invalid operator returns 422/400.
- Rule updates are visible immediately to API reads.
- Deleting rule prevents future evaluations after cache refresh.

---

## Phase 8 — WebSocket Live Stream
> Deliver tenant-isolated real-time metrics/log stream per host.

### TASK-031: Implement WebSocket endpoint `/api/v1/ws/{host_id}` [BACKEND] [M]
- Accept JWT token via query param `?token=`.
- Validate token and extract `tenant_id`.
- Verify host ownership in `app.hosts` before subscription.
- Reject unauthorized subscriptions with close code.

Test cases:
- Valid token+host opens connection.
- Token from other tenant cannot subscribe.

### TASK-032: Bridge Redis pub/sub to WebSocket clients [BACKEND] [L]
- Subscribe to `kernlog:{tenant_id}:{host_id}` and `...:logs` channels.
- Forward payloads as JSON messages with event type fields.
- Track multiple clients per host concurrently.
- Unsubscribe and cleanup on disconnect.

Test cases:
- Two clients on same host receive identical live updates.
- Disconnect removes subscriber state without leaks.

---

## Phase 9 — Alert Engine (Separate Worker)
> Deliver independent worker process for threshold alert evaluation lifecycle.

### TASK-033: Build alert engine consumer service [ALERT] [L]
- Implement standalone `alert_engine/main.py` process.
- Consume `metrics.system` and `metrics.api` with group `kernlog-alerts`.
- Parse payload and route to evaluation service.
- Add startup health log and loop resilience.

Test cases:
- Worker starts independently of FastAPI process.
- Sample metric message reaches evaluator.

### TASK-034: Implement alert rule cache and invalidation [ALERT] [M]
- Load matching rules by `(tenant_id, host_id OR global)`.
- Cache rules in-memory with 30s TTL.
- Invalidate cache on CRUD event signal.
- Skip disabled rules.

Test cases:
- Rule update becomes effective after invalidation.
- Disabled rules are never evaluated.

### TASK-035: Implement breach streak tracking and fire/resolve transitions [ALERT] [L]
- Store streak counters in Redis key `alert_streak:{tenant_id}:{host_id}:{metric}`.
- Increment on breach, reset on recovery.
- Fire alert when streak >= `consecutive` and no active alert exists.
- Resolve firing alerts when metric returns normal.
- Publish events to `kernlog:{tenant_id}:alerts`.

Test cases:
- Breach below threshold count does not fire.
- Crossing consecutive count creates firing alert.
- Recovery marks alert resolved and sets `resolved_at`.

---

## Phase 10 — Frontend Repository Setup and Onboarding
> Deliver separate Next.js repo and onboarding flow that activates first host.

### TASK-036: Initialize `kernlog-frontend` repo and baseline config [FRONTEND] [M]
- Create Next.js 14 App Router project with Tailwind.
- Install deps: `recharts`, `swr`, `js-cookie`.
- Add `.env.example` with only `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`.
- Add `README.md` with frontend-local run steps.

Test cases:
- `npm run dev` boots locally.
- Build succeeds with env vars set.

### TASK-037: Implement auth pages and token flow [FRONTEND] [L]
- Build `/signup` and `/login` pages calling backend `/auth/register` and `/auth/login`.
- Keep access token in memory and refresh path in secure cookie flow.
- Add client auth guard for protected routes.
- Redirect post-signup to `/onboarding`.

Test cases:
- Signup creates tenant and navigates to onboarding.
- Expired access token refreshes transparently.

### TASK-038: Implement onboarding page and install command [ONBOARDING] [L]
- Step 1 fetches first key via `GET /org/agent-keys` and displays one-click copy install command.
- Step 2 polls `GET /api/v1/hosts` every 3s for first heartbeat.
- Redirect to `/dashboard` when host list non-empty.
- Add error UI for key missing/poll timeout.

Test cases:
- Copy button places full command into clipboard.
- New host appearance triggers redirect automatically.

### TASK-039: Add `public/install.sh` bootstrap script [ONBOARDING] [L]
- Detect Ubuntu/Debian/CentOS package manager.
- Install Python/pip if missing.
- Install `kernlog-agent`, write `/etc/kernlog/config.yaml`, create systemd service, enable/start service.
- Accept flags `--key` and `--label`.

Test cases:
- Script fails fast when `--key` missing.
- Script creates expected config and service files.
- `systemctl status kernlog-agent` shows active after setup.

### TASK-040: Build shared API and WebSocket client libs [FRONTEND] [M]
- Implement `lib/api.ts` typed fetch wrapper to `NEXT_PUBLIC_API_URL`.
- Auto-refresh access token on 401.
- Implement `lib/ws.ts` reconnecting socket to `NEXT_PUBLIC_WS_URL/api/v1/ws/{host_id}?token=`.
- Add centralized error handling and retry policy.

Test cases:
- 401 response triggers refresh then successful replay.
- WS reconnects after temporary network loss.

---

## Phase 11 — Dashboard and Settings UI
> Deliver complete monitoring UX: hosts, metrics charts, logs, alerts, and settings.

### TASK-041: Build `/dashboard` host grid [FRONTEND] [M]
- Render host cards with label, OS, last seen, live CPU/memory/disk.
- Derive status rules: online (<60s), warning/critical from active alerts.
- Refresh host list every 30s.
- Link each card to host detail.

Test cases:
- Offline host state appears after stale heartbeat.
- Active alert changes card severity state.

### TASK-042: Build `/hosts/[id]` live metrics charts [FRONTEND] [L]
- Render 4 Recharts line charts: CPU, memory, disk, network.
- Maintain rolling last 60 points from WS stream.
- Add range picker (1h/6h/24h/7d) using REST history.
- Show active host alerts panel.

Test cases:
- Live points append without full re-render resets.
- Switching range reloads historical series correctly.

### TASK-043: Build `/hosts/[id]/logs` live viewer [FRONTEND] [M]
- Append incoming log lines from WS.
- Color severity levels (ERROR red, WARN amber, INFO default).
- Implement client-side keyword filter.
- Add pause/resume streaming toggle.

Test cases:
- Pause prevents append while preserving buffer.
- Filter shows only matching lines in buffer.

### TASK-044: Build `/alerts` table and filters [FRONTEND] [M]
- Show severity, host, metric, value, time, status columns.
- Add filters for status, severity, host.
- Implement mark-as-acknowledged action if backend endpoint exists.
- Keep polling/websocket sync behavior consistent.

Test cases:
- Filter combinations produce expected subset.
- Alert status updates reflect without full page reload.

### TASK-045: Build settings pages for rules, keys, profile [FRONTEND] [L]
- `/settings/rules`: CRUD forms for rule fields.
- `/settings/agent-keys`: list keys, generate new, reveal raw once in modal, revoke with confirm.
- `/settings/profile`: change email/password forms.
- Add optimistic updates and form validation.

Test cases:
- New key modal shows raw key once then hides permanently.
- Rule create/edit/delete updates list immediately.

---

## Phase 12 — Process Management and DX
> Deliver reproducible local workflows and debugging support without Docker.

### TASK-046: Finalize backend process/dev scripts [DEVOPS] [M]
- Ensure `scripts/create_topics.py` (or equivalent setup script) creates required Upstash QStash routes/subscriptions.
- Ensure `scripts/migrate.py` and `scripts/seed.py` are robust and logged.
- Add VS Code `.vscode/launch.json` for FastAPI, alert engine, and agent debugging.
- Validate Procfile/honcho startup path.

Test cases:
- `python scripts/create_topics.py` succeeds with valid creds.
- VS Code launch config starts each target.

### TASK-047: Finalize frontend local run docs/env [DEVOPS] [S]
- Ensure `.env.example` includes only public API/WS URL keys with comments.
- Add README steps: copy to `.env.local`, install, run dev.
- Explicitly document that local frontend points to deployed Render backend.
- Add troubleshooting section for CORS and WS URL mismatch.

Test cases:
- New developer can run frontend from README in one attempt.
- No secret env vars are required in frontend repo.

---

## Phase 13 — Hardening and Reliability
> Deliver production-safe behavior, observability, and resilience improvements.

### TASK-048: Add structured logging, request IDs, and global error format [BACKEND] [M]
- Integrate `structlog` JSON logs.
- Add request-id middleware and attach to logs.
- Implement global exception handler returning RFC 7807-style payload.
- Standardize error codes/messages.

Test cases:
- Every API log line includes request_id.
- Unhandled exception returns structured problem response.

### TASK-049: Add backend security controls and health endpoint [BACKEND] [M]
- Apply rate limiting across public endpoints.
- Lock CORS to configured frontend origin only.
- Add `/api/v1/health` endpoint.
- Document cron keep-alive setup.

Test cases:
- Disallowed origin blocked by CORS.
- Health endpoint returns 200 quickly.

### TASK-050: Add agent buffering and replay fallback [AGENT] [L]
- On repeated QStash publish failures (max 5 retries), persist payloads to local SQLite queue.
- Replay queued payloads on reconnect in order.
- Add cap/rotation policy for local buffer size.
- Log drop policy if queue is full.

Test cases:
- Simulated outage writes to SQLite queue.
- Reconnect drains queue and publishes backlog.

### TASK-051: Add frontend loading/empty/error resiliency [FRONTEND] [M]
- Add loading skeletons on all major async pages.
- Add explicit empty states (no hosts, no alerts, no rules).
- Add error boundaries and retry controls for WS/API failures.
- Improve reconnect UX messaging.

Test cases:
- Empty tenant shows onboarding-like empty states.
- WS disconnect displays retry UI and recovers automatically.

### TASK-052: Finalize documentation set [DEVOPS] [M]
- Expand root READMEs with architecture, setup, deployment, env vars, and install guide.
- Include free-tier caveats and scaling notes.
- Add troubleshooting for auth, QStash, Redis, and Render sleep behavior.
- Add sequence diagrams (text/mermaid) for ingestion and alert flow.

Test cases:
- Fresh developer can follow docs from clone to running stack.
- Env var table covers all runtime components.

---

## Phase 14 — Production Deployment (Free Tier)
> Deliver deployed end-to-end SaaS across Neon, Upstash, Render, Vercel, and cron keep-alive.

### TASK-053: Deploy and configure Neon [INFRA] [M]
- Create Neon project/db and set pooled/direct URLs appropriately.
- Run migrations and seed with production-safe controls.
- Validate `app` and `metrics` schema objects in prod.
- Configure retention/backup expectations.

Test cases:
- Production DB reachable from backend.
- Migration history matches expected head.

### TASK-054: Deploy and configure Upstash QStash + Redis [INFRA] [M]
- Create QStash routes/subscriptions for `metrics.system`, `metrics.api`, `logs.app`.
- Configure QStash creds for backend, worker, and agent template.
- Configure Redis REST creds and verify key/channel operations.
- Validate regional alignment with Neon.

Test cases:
- Test publish/consume works for all topics.
- Redis set/get/pubsub succeeds from app runtime.

### TASK-055: Deploy backend and alert engine to Render [DEVOPS] [L]
- Create Render Web Service for FastAPI and Worker for alert engine.
- Set env vars and start commands.
- Validate health endpoint and ingestion loop post-deploy.
- Tune polling/idle behavior for free tier constraints.

Test cases:
- Backend serves auth and protected endpoints in production.
- Worker consumes metrics and emits alerts.

### TASK-056: Deploy frontend to Vercel and connect CORS [DEVOPS] [M]
- Import `kernlog-frontend` repo into Vercel.
- Set public API/WS env vars to Render backend.
- Confirm `public/install.sh` is served.
- Update backend `CORS_ORIGIN` to Vercel URL/custom domain.

Test cases:
- Signup/login works on deployed frontend.
- Install script downloadable from Vercel URL.

### TASK-057: Configure cron keep-alive and production validation checklist [DEVOPS] [S]
- Add cron-job.org ping every 10 minutes to `/api/v1/health`.
- Optionally add worker health ping.
- Write final go-live checklist: auth, agent registration, live metrics, logs, alert fire/resolve, multi-tenant isolation.
- Capture baseline free-tier usage telemetry.

Test cases:
- Render backend does not cold-start during active cron period.
- End-to-end smoke checklist passes in production.

---

## Full Database Schema (Canonical)

```sql
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS metrics;

CREATE TABLE IF NOT EXISTS app.organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  plan TEXT NOT NULL DEFAULT 'free',
  host_limit INT NOT NULL DEFAULT 5,
  retention_days INT NOT NULL DEFAULT 7,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.refresh_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL,
  token_hash TEXT UNIQUE NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.agent_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
  key_hash TEXT UNIQUE NOT NULL,
  key_prefix TEXT NOT NULL,
  label TEXT,
  last_used_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.hosts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
  host_id TEXT NOT NULL,
  label TEXT,
  os TEXT,
  arch TEXT,
  agent_version TEXT,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, host_id)
);

CREATE TABLE IF NOT EXISTS app.alert_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
  host_id TEXT,
  metric_name TEXT NOT NULL,
  operator TEXT NOT NULL,
  threshold DOUBLE PRECISION NOT NULL,
  consecutive INT NOT NULL DEFAULT 3,
  severity TEXT NOT NULL DEFAULT 'warning',
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
  rule_id UUID REFERENCES app.alert_rules(id) ON DELETE SET NULL,
  host_id TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'firing',
  fired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS metrics.metrics (
  time TIMESTAMPTZ NOT NULL DEFAULT now(),
  tenant_id UUID NOT NULL,
  host_id TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  tags JSONB
);

CREATE INDEX IF NOT EXISTS idx_metrics_lookup
  ON metrics.metrics (tenant_id, host_id, metric_name, time DESC);

CREATE TABLE IF NOT EXISTS metrics.logs (
  time TIMESTAMPTZ NOT NULL DEFAULT now(),
  tenant_id UUID NOT NULL,
  host_id TEXT NOT NULL,
  file_path TEXT,
  line TEXT NOT NULL,
  severity TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_lookup
  ON metrics.logs (tenant_id, host_id, time DESC);
```
