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
    assert "Run schema, lookup, auth, session, and log-import persistence tests" in database_notes
    assert "Switch local development defaults from MySQL to Postgres" in database_notes
