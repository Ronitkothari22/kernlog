"""phase7 alert rules columns and query indexes

Revision ID: 20260530_02
Revises: 20260530_01
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op


revision = "20260530_02"
down_revision = "20260530_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.alert_rules ADD COLUMN IF NOT EXISTS operator text")
    op.execute("ALTER TABLE app.alert_rules ADD COLUMN IF NOT EXISTS severity text NOT NULL DEFAULT 'warning'")
    op.execute("ALTER TABLE app.alert_rules ADD COLUMN IF NOT EXISTS host_id text")
    op.execute("UPDATE app.alert_rules SET operator = comparator WHERE operator IS NULL")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hosts_tenant_last_seen ON app.hosts (tenant_id, last_seen_at DESC, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_query ON metrics.metrics (tenant_id, host_id, metric_name, ts DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_query ON metrics.logs (tenant_id, host_id, severity, ts DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_alerts_query ON app.alerts (tenant_id, status, host_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_alert_rules_tenant_created ON app.alert_rules (tenant_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alert_rules_tenant_created")
    op.execute("DROP INDEX IF EXISTS idx_alerts_query")
    op.execute("DROP INDEX IF EXISTS idx_logs_query")
    op.execute("DROP INDEX IF EXISTS idx_metrics_query")
    op.execute("DROP INDEX IF EXISTS idx_hosts_tenant_last_seen")

    op.execute("ALTER TABLE app.alert_rules DROP COLUMN IF EXISTS host_id")
    op.execute("ALTER TABLE app.alert_rules DROP COLUMN IF EXISTS severity")
    op.execute("ALTER TABLE app.alert_rules DROP COLUMN IF EXISTS operator")
