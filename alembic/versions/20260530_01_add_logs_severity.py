"""add severity column to metrics.logs

Revision ID: 20260530_01
Revises: 20260529_01
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op


revision = "20260530_01"
down_revision = "20260529_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE metrics.logs ADD COLUMN IF NOT EXISTS severity text NOT NULL DEFAULT 'INFO'")


def downgrade() -> None:
    op.execute("ALTER TABLE metrics.logs DROP COLUMN IF EXISTS severity")
