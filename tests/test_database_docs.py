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
    assert "Document the production deployment and rollback gate" in database_notes
    assert "Add tested MySQL-to-Postgres import tooling" in database_notes
    assert "Remove MySQL-only dependencies" in database_notes


def test_postgres_cutover_docs_define_rollback_gate() -> None:
    plans = (REPOSITORY_ROOT / "PLANS.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()
    agent_notes = (REPOSITORY_ROOT / "AGENTS.md").read_text()

    assert "Postgres is the default local Docker database" in agent_notes
    assert "rollback planning" in agent_notes
    assert "deployment and rollback gate" in plans
    assert (
        "Remove MySQL-only runtime paths after deployment and rollback plans are\n"
        "     documented. Pending."
    ) in plans
    assert "Production Cutover And Rollback Gate" in database_notes
    assert "Cutover Preconditions" in database_notes
    assert "Deployment Plan" in database_notes
    assert "Rollback Plan" in database_notes
    assert "Runtime Cleanup Rules" in database_notes
    assert "dual-write" in database_notes
    assert "Remove the legacy `MYSQL_*` ORM fallback only after" in database_notes


def test_postgres_import_tooling_docs_require_rehearsal_guardrails() -> None:
    plans = (REPOSITORY_ROOT / "PLANS.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()

    assert "import tooling for cutover rehearsals" in plans
    assert "real backup rehearsal remains pending" in plans
    assert "Docker-backed MySQL-to-Postgres" in plans
    assert "server/import_mysql_to_postgres.py" in database_notes
    assert "Import Rehearsal Command" in database_notes
    assert "--dry-run" in database_notes
    assert "preserves primary keys" in database_notes
    assert "Other target tables must be empty" in database_notes
    assert "Postgres marker suite runs a Docker-backed rehearsal" in database_notes
    assert "primary-key sequences advance" in database_notes
    assert "Python auth rules" in database_notes
    assert "ORM\nlookup helpers" in database_notes


def test_local_database_setup_docs_use_alembic_command() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    local_development = (REPOSITORY_ROOT / "docs" / "local-development.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()

    assert "python setup_database.py" in readme
    assert "python setup_database.py" in local_development
    assert "server/setup_database.py" in database_notes
    assert "python initialize_database.py" not in readme
    assert "python initialize_database.py" not in local_development
