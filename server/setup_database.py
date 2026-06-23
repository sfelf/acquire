"""Apply database migrations for local development and test setup."""

from pathlib import Path

from alembic import command
from alembic.config import Config

REPO_DIR = Path(__file__).resolve().parents[1]


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


def main() -> None:
    """Upgrade the configured database to the latest Alembic revision."""
    command.upgrade(alembic_config(), "head")


if __name__ == "__main__":
    main()
