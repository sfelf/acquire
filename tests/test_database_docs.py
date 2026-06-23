from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_phase_6_tracks_postgres_migration_sequence() -> None:
    plans = (REPOSITORY_ROOT / "PLANS.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()

    assert "Add Alembic migrations for the current MySQL schema" in plans
    assert "engines. Complete." in plans
    assert "MySQL-to-Postgres migration" in plans
    assert "In progress." in plans
    assert "Postgres Migration Sequence" in database_notes
    assert "Add Postgres test dependencies" in database_notes
    assert "Add a `postgres` pytest marker" in database_notes
    assert "Run schema, lookup, auth, session, and log-import persistence tests" in database_notes
    assert "Switch local development defaults from MySQL to Postgres" in database_notes


def test_local_database_setup_docs_use_alembic_command() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    local_development = (REPOSITORY_ROOT / "docs" / "local-development.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()

    assert "python setup_database.py" in readme
    assert "python setup_database.py" in local_development
    assert "server/setup_database.py" in database_notes
    assert "python initialize_database.py" not in readme
    assert "python initialize_database.py" not in local_development
