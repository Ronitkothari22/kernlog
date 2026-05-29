"""Run Alembic migrations to latest revision."""

from __future__ import annotations

from pathlib import Path
import os

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    load_dotenv()
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
