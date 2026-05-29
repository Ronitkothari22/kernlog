"""Seed script for dev tenant, owner, and agent key."""

from __future__ import annotations

import hashlib
import secrets
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import text

ORG_NAME = "Test Org"
ORG_SLUG = "test-org"
OWNER_EMAIL = "dev@kernlog.io"
OWNER_PASSWORD = "devpassword"
AGENT_LABEL = "dev-seed-key"


def _make_agent_key() -> tuple[str, str, str]:
    raw = f"kl_live_{secrets.token_urlsafe(24)}"
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    prefix = raw[:14]
    return raw, key_hash, prefix


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    load_dotenv()
    from app.db import SessionLocal
    from app.security import hash_password

    db = SessionLocal()
    try:
        org = db.execute(
            text("SELECT id FROM app.organizations WHERE slug = :slug"),
            {"slug": ORG_SLUG},
        ).first()
        if not org:
            org = db.execute(
                text("INSERT INTO app.organizations (name, slug) VALUES (:name, :slug) RETURNING id"),
                {"name": ORG_NAME, "slug": ORG_SLUG},
            ).first()
            print("created organization test-org")
        else:
            print("organization test-org already exists")

        user = db.execute(
            text("SELECT id FROM app.users WHERE email = :email"),
            {"email": OWNER_EMAIL},
        ).first()
        if not user:
            db.execute(
                text(
                    """
                    INSERT INTO app.users (tenant_id, email, password_hash, role)
                    VALUES (:tenant_id, :email, :password_hash, 'owner')
                    """
                ),
                {
                    "tenant_id": org.id,
                    "email": OWNER_EMAIL,
                    "password_hash": hash_password(OWNER_PASSWORD),
                },
            )
            print("created user dev@kernlog.io")
        else:
            print("user dev@kernlog.io already exists")

        existing_key = db.execute(
            text("SELECT id FROM app.agent_keys WHERE tenant_id = :tenant_id AND label = :label"),
            {"tenant_id": org.id, "label": AGENT_LABEL},
        ).first()
        if not existing_key:
            raw, key_hash, prefix = _make_agent_key()
            db.execute(
                text(
                    """
                    INSERT INTO app.agent_keys (tenant_id, key_hash, key_prefix, label)
                    VALUES (:tenant_id, :key_hash, :key_prefix, :label)
                    """
                ),
                {
                    "tenant_id": org.id,
                    "key_hash": key_hash,
                    "key_prefix": prefix,
                    "label": AGENT_LABEL,
                },
            )
            print(f"created agent key (shown once): {raw}")
        else:
            print("agent key already exists for dev seed label")

        db.commit()
        print("seed complete")
    finally:
        db.close()
