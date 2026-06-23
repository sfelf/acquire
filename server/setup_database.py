"""Apply database migrations for local development and test setup."""

from pathlib import Path

import orm
import sqlalchemy
from alembic import command
from alembic.config import Config

REPO_DIR = Path(__file__).resolve().parents[1]
BASELINE_TABLES = {
    "game",
    "game_mode",
    "game_player",
    "game_state",
    "key_value",
    "rating",
    "rating_type",
    "record",
    "user",
}


def alembic_config() -> Config:
    """Return the repository Alembic configuration.

    The local Docker image runs this module from `/app/server`, while local
    developer commands may run it from other directories. Resolving the config
    relative to this file keeps the setup command independent of the current
    working directory.

    Returns:
        Alembic config for the repository migration environment.
    """
    config = Config(str(REPO_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_DIR / "migrations"))
    return config


def is_unstamped_legacy_schema() -> bool:
    """Return whether the database has the baseline schema but no Alembic stamp.

    Local development databases created by the legacy `initialize_database.py`
    command already contain the baseline application tables but do not contain
    Alembic's version table. Stamping those databases before upgrade lets them
    move onto the migration path without dropping local data.

    Returns:
        `True` when all baseline application tables exist and `alembic_version`
        is absent.
    """
    inspector = sqlalchemy.inspect(orm.engine)
    table_names = set(inspector.get_table_names())
    return "alembic_version" not in table_names and table_names >= BASELINE_TABLES


def stamp_legacy_schema(config: Config) -> None:
    """Stamp a matching legacy schema as the Alembic baseline when needed.

    Args:
        config: Alembic configuration for the repository migration environment.
    """
    if is_unstamped_legacy_schema():
        command.stamp(config, "head")


def main() -> None:
    """Upgrade the configured database to the latest Alembic revision."""
    config = alembic_config()
    stamp_legacy_schema(config)
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
