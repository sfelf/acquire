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
    backup_runbook = (
        REPOSITORY_ROOT / "docs" / "postgres-backup-rehearsal.md"
    ).read_text()

    assert "import tooling for cutover rehearsals" in plans
    assert "61 sanitized report rows" in plans
    assert "sanitized or staging backup rehearsal runbook. Complete." in plans
    assert "Run the import rehearsal against a sanitized or staging MySQL backup." in plans
    assert "Complete with an accepted sparse-stats limitation" in plans
    assert "not possible from the current\n     server backup" in plans
    assert "retain\n     `--require-source-rows`" in plans
    assert "Keep the MySQL-to-Postgres backup import tooling" in plans
    assert "Docker-backed MySQL-to-Postgres" in plans
    assert "server/import_mysql_to_postgres.py" in database_notes
    assert "can require the derived `record` table" in database_notes
    assert "docs/postgres-backup-rehearsal.md" in database_notes
    assert "Import Rehearsal Command" in database_notes
    assert "--dry-run" in database_notes
    assert "preserves primary keys" in database_notes
    assert "Other target tables must be empty" in database_notes
    assert "`--require-source-rows rating --require-source-rows record`" in database_notes
    assert "fail before target rows are\ncopied" in database_notes
    assert "Postgres marker suite runs a Docker-backed rehearsal" in database_notes
    assert "primary-key sequences advance" in database_notes
    assert "Python auth rules" in database_notes
    assert "ORM\nlookup helpers" in database_notes
    assert "partial staging backup rehearsal completed with\n   sanitized reports" in database_notes
    assert "game-history rows and stats read paths" in database_notes
    assert "sparse-stats limitation is accepted for the current migration evidence" in (
        database_notes
    )
    assert "Retain the MySQL-to-Postgres backup import tool" in database_notes
    assert "Keep the MySQL-to-Postgres backup import tool" in database_notes
    assert "persisted rating/record evidence is explicitly unavailable" in database_notes
    assert "keep backup files outside the repository" in backup_runbook
    assert "Do not commit dumps" in backup_runbook
    assert "Source Readiness Check" in backup_runbook
    assert "select 'rating' as table_name, count(*) as row_count from rating" in (
        backup_runbook
    )
    assert "select 'record' as table_name, count(*) as row_count from record" in (
        backup_runbook
    )
    assert "Both counts must be greater than zero" in backup_runbook
    assert "When\nthe server never generated persisted stats" in backup_runbook
    assert "do not claim persisted rating or derived-record coverage" in (
        backup_runbook
    )
    assert "For a partial sparse-source rehearsal" in backup_runbook
    assert (
        "omit\n`--require-source-rows rating` and `--require-source-rows record`"
        in backup_runbook
    )
    assert "Record the missing source tables in the\nrehearsal summary" in backup_runbook
    assert "Do not use a partial sparse-source rehearsal as production\ncutover evidence" in (
        backup_runbook
    )
    assert "source readiness check for nonzero `rating` and `record`" in database_notes
    assert "ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432" in (
        backup_runbook
    )
    assert "--source-url mysql+mysqlconnector://user:password@host:3306" in (
        backup_runbook
    )
    assert "mysql+pymysql" not in backup_runbook
    assert "--target-url postgresql+psycopg://user:password@host:5432" in (
        backup_runbook
    )
    assert "--report-json /tmp/acquire-rehearsal/dry-run-report.json" in backup_runbook
    assert "--report-json /tmp/acquire-rehearsal/import-report.json" in backup_runbook
    assert "fail before target rows are copied" in backup_runbook
    assert "must not include connection URLs, credentials" in backup_runbook
    assert "dry-run JSON report records source row counts" in backup_runbook
    assert "server/validate_import_reports.py" in backup_runbook
    assert "--dry-run-report /tmp/acquire-rehearsal/dry-run-report.json" in backup_runbook
    assert "--import-report /tmp/acquire-rehearsal/import-report.json" in backup_runbook
    assert "--require-source-rows rating" in backup_runbook
    assert "--require-source-rows record" in backup_runbook
    assert "sparse source dump that lacks\n   persisted rating history" in backup_runbook
    assert "separate\n   disposable test databases" in backup_runbook
    assert "Do not point marker test URLs at the restored\n   MySQL source" in (
        backup_runbook
    )
    assert "docker compose --profile client-build run --rm client-assets" in (
        backup_runbook
    )
    assert "gateway.override.yml" in backup_runbook
    assert "host.docker.internal:host-gateway" in backup_runbook
    assert "docker compose -f docker-compose.yml" in backup_runbook
    assert "run --rm --service-ports --no-deps" in backup_runbook
    assert "host.docker.internal:5432/acquire_rehearsal" in backup_runbook
    assert "reachable from\n   inside the gateway container" in backup_runbook
    assert "Docker Desktop users may omit the temporary\n   override" in backup_runbook
    assert "`ACQUIRE_E2E_URL` is unset, the default Docker-backed e2e fixture" in (
        backup_runbook.replace("\n   ", " ")
    )
    assert "ACQUIRE_E2E_URL" in backup_runbook
    assert "Pass Criteria" in backup_runbook
    assert "Completed-game rating checks pass when the source generated persisted rating" in (
        backup_runbook
    )
    assert "otherwise the rehearsal records the sparse-stats limitation" in backup_runbook
    assert "Failure Handling" in backup_runbook


def test_local_database_setup_docs_use_alembic_command() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    local_development = (REPOSITORY_ROOT / "docs" / "local-development.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()

    assert not (REPOSITORY_ROOT / "server" / "initialize_database.py").exists()
    assert "python setup_database.py" in readme
    assert "python setup_database.py" in local_development
    assert "server/setup_database.py" in database_notes
    assert "The legacy MySQL reset command has been removed" in database_notes
    assert "python initialize_database.py" not in readme
    assert "python initialize_database.py" not in local_development
