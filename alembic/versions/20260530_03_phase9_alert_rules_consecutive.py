"""phase9 add alert_rules consecutive

Revision ID: 20260530_03
Revises: 20260530_02
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260530_03"
down_revision = "20260530_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.alert_rules ADD COLUMN IF NOT EXISTS consecutive integer NOT NULL DEFAULT 3")


def downgrade() -> None:
    op.execute("ALTER TABLE app.alert_rules DROP COLUMN IF EXISTS consecutive")
