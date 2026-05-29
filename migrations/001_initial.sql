CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS metrics;

CREATE TABLE IF NOT EXISTS app.organizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    slug text NOT NULL UNIQUE,
    plan text NOT NULL DEFAULT 'free',
    host_limit integer NOT NULL DEFAULT 10,
    retention_days integer NOT NULL DEFAULT 7,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'member',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.refresh_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    replaced_by_token_hash text,
    last_used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.agent_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
    key_hash text NOT NULL UNIQUE,
    key_prefix text NOT NULL,
    label text,
    last_used_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.hosts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
    host_id text NOT NULL,
    label text,
    os text,
    arch text,
    agent_version text,
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, host_id)
);

CREATE TABLE IF NOT EXISTS app.alert_rules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
    name text NOT NULL,
    metric_name text NOT NULL,
    comparator text NOT NULL,
    threshold double precision NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.alerts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES app.organizations(id) ON DELETE CASCADE,
    rule_id uuid REFERENCES app.alert_rules(id) ON DELETE SET NULL,
    host_id text,
    severity text NOT NULL DEFAULT 'warning',
    message text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE TABLE IF NOT EXISTS metrics.metrics (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    host_id text NOT NULL,
    metric_name text NOT NULL,
    metric_value double precision NOT NULL,
    labels jsonb NOT NULL DEFAULT '{}'::jsonb,
    ts timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS metrics.logs (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    host_id text NOT NULL,
    file_path text,
    line text NOT NULL,
    ts timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metrics_lookup
    ON metrics.metrics (tenant_id, host_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_logs_lookup
    ON metrics.logs (tenant_id, host_id, ts DESC);
