"""Apply packaged database migrations for development and deployment setup.

This module owns the installed command and guarded legacy-schema stamp used by
local, test, and production database setup. Migration configuration and scripts
are resolved from package resources, independent of the current working
directory.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Never

import sqlalchemy
from sqlalchemy.engine.reflection import Inspector

from acquire import orm

if TYPE_CHECKING:  # pragma: no cover
    from alembic.config import Config

RESOURCE_PACKAGE = "acquire"
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
    """Return the Alembic configuration from installed package resources.

    Returns:
        Alembic config for the packaged migration environment.

    Raises:
        RuntimeError: Required package resources are unavailable.
    """
    package_root = resources.files(RESOURCE_PACKAGE)
    config_path = Path(str(package_root.joinpath("alembic.ini")))
    migrations_path = Path(str(package_root.joinpath("migrations")))
    if not config_path.is_file() or not migrations_path.is_dir():
        raise RuntimeError("Database setup requires installed migration resources.")

    from alembic.config import Config

    config = Config(str(config_path))
    config.set_main_option("script_location", str(migrations_path))
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

    Only the exact legacy table, column, and lookup-row shape is stamped.
    Empty, versioned, partial, and unknown schemas remain unstamped so Alembic
    owns their normal upgrade or failure behavior.

    Args:
        config: Alembic configuration for the packaged migration environment.
    """
    if is_unstamped_legacy_schema():
        from alembic import command

        command.stamp(config, BASELINE_REVISION)


def run_setup() -> None:
    """Upgrade the configured database to the latest Alembic revision.

    A precisely matching unstamped legacy schema is stamped at the baseline
    before upgrade. Empty, already versioned, partial, or unknown schemas are
    passed to Alembic without a synthetic stamp so migration errors remain
    visible to programmatic callers. Repeated successful calls are safe.
    """
    config = alembic_config()
    stamp_legacy_schema(config)
    from alembic import command

    command.upgrade(config, "head")


class SetupArgumentParser(argparse.ArgumentParser):
    """Parse the no-argument setup command without reflecting unsafe input."""

    def error(self, message: str) -> Never:
        """Exit with a fixed diagnostic for invalid command arguments.

        Argument text is operator-controlled and may contain credentials or
        private identifiers, so the parser never projects the input or the
        generated argparse message.

        Args:
            message: Argparse-generated error text, intentionally ignored.
        """
        self.exit(2, "error: invalid arguments\n")


def parse_args(argv: Sequence[str] | None = None) -> None:
    """Validate the database-setup command arguments.

    Args:
        argv: Arguments to parse, or `None` to use the process arguments.
    """
    parser = SetupArgumentParser(
        prog="acquire-setup-database",
        description="Upgrade the configured Acquire database to the latest revision.",
    )
    parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the installed database-setup command.

    Database selection remains environment-driven through `acquire.orm`.
    Invalid arguments exit through argparse with status 2. Resource, inspection,
    connection, and migration failures return status 1 with a fixed diagnostic
    so database URLs and exception representations cannot reach command output.

    Args:
        argv: Arguments to parse, or `None` to use the process arguments.

    Returns:
        `0` after a successful upgrade, or `1` after a setup failure.
    """
    parse_args(argv)
    try:
        run_setup()
    except Exception:
        print("error: database setup failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
