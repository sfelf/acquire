"""Apply database migrations for local development and deployment setup.

This module owns the guarded legacy-schema stamp and Alembic upgrade workflow
used by local, test, and production database setup.
"""

from pathlib import Path

import sqlalchemy
from alembic import command
from alembic.config import Config
from sqlalchemy.engine.reflection import Inspector

from acquire import orm

REPO_DIR = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "20260622_0001"
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
BASELINE_COLUMNS = {
    "game": {
        "game_id",
        "log_time",
        "number",
        "begin_time",
        "end_time",
        "game_state_id",
        "game_mode_id",
    },
    "game_mode": {"game_mode_id", "name"},
    "game_player": {
        "game_player_id",
        "game_id",
        "player_index",
        "user_id",
        "score",
    },
    "game_state": {"game_state_id", "name"},
    "key_value": {"key_value_id", "key", "value"},
    "rating": {"rating_id", "user_id", "rating_type_id", "time", "mu", "sigma"},
    "rating_type": {"rating_type_id", "name"},
    "record": {"user_id", "encoded"},
    "user": {"user_id", "name", "password"},
}
BASELINE_LOOKUP_ROWS = {
    "game_mode": {"Singles", "Teams"},
    "game_state": {"Starting", "StartingFull", "InProgress", "Completed"},
    "rating_type": {"Singles2", "Singles3", "Singles4", "Teams"},
}


def alembic_config() -> Config:
    """Return the repository Alembic configuration.

    The current direct-file and editable-install commands use migrations stored
    at the repository root. Resolving them relative to the packaged source
    module keeps setup independent of the current working directory. Issue
    #110 owns the installed project command, and issue #111 owns the final
    artifact layout.

    Returns:
        Alembic config for the repository migration environment.
    """
    config = Config(str(REPO_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_DIR / "migrations"))
    return config


def is_unstamped_legacy_schema() -> bool:
    """Return whether the database has the baseline schema but no Alembic stamp.

    Local development databases created by the pre-Alembic reset command
    already contain the baseline application tables but do not contain
    Alembic's version table. Stamping those databases before upgrade lets them
    move onto the migration path without dropping local data.

    Returns:
        `True` when the baseline application tables, expected columns, and
        required lookup rows exist and `alembic_version` is absent.
    """
    inspector = sqlalchemy.inspect(orm.engine)
    table_names = set(inspector.get_table_names())
    return (
        "alembic_version" not in table_names
        and table_names == BASELINE_TABLES
        and has_baseline_columns(inspector)
        and has_baseline_lookup_rows()
    )


def has_baseline_columns(inspector: Inspector) -> bool:
    """Return whether all baseline tables have the expected column names.

    Args:
        inspector: SQLAlchemy inspector for the configured database.

    Returns:
        `True` when each baseline table has exactly the expected columns.
    """
    return all(
        {column["name"] for column in inspector.get_columns(table_name)}
        == expected_columns
        for table_name, expected_columns in BASELINE_COLUMNS.items()
    )


def has_baseline_lookup_rows() -> bool:
    """Return whether required baseline lookup rows are present.

    Returns:
        `True` when the legacy schema contains exactly the lookup rows inserted
        by the baseline migration.
    """
    with orm.engine.connect() as connection:
        for table_name, expected_names in BASELINE_LOOKUP_ROWS.items():
            rows = connection.execute(sqlalchemy.text(f"select name from {table_name}"))
            if {row[0] for row in rows} != expected_names:
                return False
    return True


def stamp_legacy_schema(config: Config) -> None:
    """Stamp a matching legacy schema as the Alembic baseline when needed.

    Args:
        config: Alembic configuration for the repository migration environment.
    """
    if is_unstamped_legacy_schema():
        command.stamp(config, BASELINE_REVISION)


def main() -> None:
    """Upgrade the configured database to the latest Alembic revision.

    A precisely matching unstamped legacy schema is stamped at the baseline
    before upgrade. Empty, already versioned, partial, or unknown schemas are
    passed to Alembic without a synthetic stamp so migration errors remain
    visible at the owning boundary. Repeated successful calls are safe.
    """
    config = alembic_config()
    stamp_legacy_schema(config)
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
