"""Configure Alembic for the Acquire database schema."""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path
from typing import cast

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection, Engine

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import orm  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = orm.Base.metadata


def get_configured_url() -> str:
    """Return the configured database URL for Alembic commands.

    Tests can set `sqlalchemy.url` directly on the Alembic config. Normal local
    commands fall back to the same URL assembled by `server/orm.py`, preserving
    the existing MySQL environment-variable behavior.

    Returns:
        Configured Alembic URL or the ORM-derived runtime URL.
    """
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url
    return orm.engine.url.render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=get_configured_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def get_connectable() -> Connection | Engine:
    """Return the injected connection or create an Alembic engine.

    The test suite injects a connection so migrations run against the same
    Docker-backed database fixture. CLI commands use `server/orm.py`'s engine
    when no URL is supplied, which keeps MySQL socket and auth plugin settings
    aligned with the legacy runtime.

    Returns:
        Injected SQLAlchemy connection, configured engine, or ORM runtime engine.
    """
    connection = config.attributes.get("connection")
    if connection is not None:
        return cast(Connection, connection)

    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return create_engine(configured_url, poolclass=pool.NullPool)

    return orm.engine


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = get_connectable()
    if isinstance(connectable, Connection):
        context.configure(connection=connectable, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
