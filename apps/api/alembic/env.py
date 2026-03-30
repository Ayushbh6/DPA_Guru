from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Ensure the repo root and apps/api/src are importable for metadata discovery.
REPO_ROOT = Path(__file__).resolve().parents[3]
API_SRC = REPO_ROOT / "apps" / "api" / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(API_SRC))

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "apps" / "api" / ".env")

from db.base import Base  # noqa: E402
import db.models  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = (os.getenv("DATABASE_URL") or "").strip()
configured_url = (config.get_main_option("sqlalchemy.url") or "").strip()

# Prefer an explicitly configured Alembic URL (e.g. tests set this programmatically).
# Otherwise require DATABASE_URL from the environment.
if not configured_url:
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required for Alembic migrations. "
        )
    config.set_main_option("sqlalchemy.url", database_url)

active_url = (config.get_main_option("sqlalchemy.url") or "").strip()
if active_url.startswith("postgresql://"):
    config.set_main_option(
        "sqlalchemy.url",
        active_url.replace("postgresql://", "postgresql+psycopg://", 1),
    )

target_metadata = Base.metadata


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    url = _normalize_database_url(config.get_main_option("sqlalchemy.url"))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = dict(config.get_section(config.config_ini_section, {}))
    section["sqlalchemy.url"] = _normalize_database_url(
        section.get("sqlalchemy.url") or config.get_main_option("sqlalchemy.url")
    )
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
