"""initial schemas and tables

Revision ID: 20260529_01
Revises:
Create Date: 2026-05-29
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "20260529_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = Path(__file__).resolve().parents[2] / "migrations" / "001_initial.sql"
    op.execute(sql_path.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS metrics CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE;")
