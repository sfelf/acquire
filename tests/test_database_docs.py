from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_readme_identifies_independent_fork_and_hosted_original() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()

    assert "[tlstyer/acquire](https://github.com/tlstyer/acquire)" in readme
    assert "[acquire.tlstyer.com](http://acquire.tlstyer.com/)" in readme
    assert "We are grateful to tlstyer and the\nproject's contributors" in readme
    assert "not affiliated with, endorsed by, or maintained in collaboration" in readme
    assert "not the source currently deployed at\n`acquire.tlstyer.com`" in readme


def test_plans_preserve_completed_modernization_and_packaging_status() -> None:
    plans = (REPOSITORY_ROOT / "PLANS.md").read_text()
    agent_notes = (REPOSITORY_ROOT / "AGENTS.md").read_text()

    assert plans.startswith("# Modernization And Packaging Plan\n")
    assert "The six-phase modernization plan is complete as of July 23, 2026." in plans
    assert "The Packaging milestone is complete." in plans
    assert "[#103](https://github.com/sfelf/acquire/issues/103)," in plans
    assert "[#104](https://github.com/sfelf/acquire/issues/104)," in plans
    assert "[#111](https://github.com/sfelf/acquire/issues/111), and" in plans
    assert "[#127](https://github.com/sfelf/acquire/issues/127) are complete" in plans
    assert "Issue #105 is delivered as three stand-alone PR slices" in plans
    assert "Issue #110 is also delivered as three stand-alone PR slices" in plans
    assert "GitHub issues remain the source of\ntruth for issue scope" in plans
    assert "Runtime dependency upgrades are intentionally deferred." not in plans
    assert "The six-phase modernization plan is complete." in agent_notes
    assert "Follow GitHub issues and milestones for the next major-refactor work" in (
        agent_notes
    )
    assert "GitHub issues and milestones\nremain authoritative" in agent_notes
    assert "update `PLANS.md` when an approved issue change" in agent_notes
    assert "Keep linting and type checking permissive" not in agent_notes


def test_phase_6_tracks_postgres_migration_sequence() -> None:
    plans = (REPOSITORY_ROOT / "PLANS.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()

    assert "## Phase 6: Dependency And Deployment Modernization" in plans
    assert "Status: complete." in plans
    assert "Add Alembic migrations for the current MySQL schema" in plans
    assert "engines. Complete." in plans
    assert "MySQL-to-Postgres migration" in plans
    assert "persistence tests are in place. Complete." in plans
    assert "Postgres Migration Sequence" in database_notes
    assert "Add Postgres test dependencies" in database_notes
    assert "Add a `postgres` pytest marker" in database_notes
    assert "Run schema, lookup, auth, session, and log-import persistence tests" in database_notes
    assert "Switch local development defaults from MySQL to Postgres" in database_notes
    assert "Document the production deployment and rollback gate" in database_notes
    assert "Add tested MySQL-to-Postgres import tooling" in database_notes
    assert "Remove MySQL-only runtime dependencies" in database_notes
    assert "variables, marker tests, and runtime documentation. Complete." in database_notes


def test_postgres_runtime_docs_define_retained_backup_boundary() -> None:
    plans = (REPOSITORY_ROOT / "PLANS.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()
    agent_notes = (REPOSITORY_ROOT / "AGENTS.md").read_text()

    assert "Postgres is the only application runtime database" in agent_notes
    assert "`mysql-migration` optional uv extra" in agent_notes
    assert "deployment and rollback gate" in plans
    assert (
        "Remove MySQL-only runtime paths after deployment and rollback plans are\n"
        "     documented. Complete."
    ) in plans
    assert "Backup Import And Deployment Gate" in database_notes
    assert "Cutover Preconditions" in database_notes
    assert "Deployment Plan" in database_notes
    assert "Rollback Plan" in database_notes
    assert "Retained Migration Rules" in database_notes
    assert "dual-write" in database_notes
    assert "no MySQL runtime\n  fallback" in database_notes
    assert "normal development and production runtime\n  dependencies do not install" in (
        database_notes
    )


def test_postgres_import_tooling_docs_require_rehearsal_guardrails() -> None:
    plans = (REPOSITORY_ROOT / "PLANS.md").read_text()
    database_notes = (REPOSITORY_ROOT / "docs" / "database.md").read_text()
    backup_runbook = (
        REPOSITORY_ROOT / "docs" / "postgres-backup-rehearsal.md"
    ).read_text()
    normalized_database_notes = " ".join(database_notes.split())
    normalized_backup_runbook = " ".join(backup_runbook.split())

    assert "import tooling for cutover rehearsals" in plans
    assert "61 sanitized report rows" in plans
    assert "sanitized or staging backup rehearsal runbook. Complete." in plans
    assert "Run the import rehearsal against a sanitized or staging MySQL backup." in plans
    assert "Complete with an accepted sparse-stats limitation" in plans
    assert "not possible from the current server\n     backup" in plans
    assert "restored source still included every table required by the\n     importer" in plans
    assert "retain\n     `--require-source-rows`" in plans
    assert "Keep the\n     MySQL-to-Postgres backup import tooling" in plans
    assert "`mysql-migration` optional uv extra" in plans
    assert "acquire.migration.import_mysql_to_postgres" in database_notes
    assert "acquire-migrate-mysql-to-postgres" in database_notes
    assert "acquire-validate-migration-reports" in database_notes
    assert "requires every application table, including the derived `record` table" in (
        normalized_database_notes
    )
    assert "optional `--require-source-rows` checks require selected tables" in (
        normalized_database_notes
    )
    assert "docs/postgres-backup-rehearsal.md" in database_notes
    assert "Import Rehearsal Command" in database_notes
    assert "--dry-run" in database_notes
    assert "preserves primary keys" in database_notes
    assert "Other target tables must be empty" in database_notes
    assert "`--require-source-rows rating --require-source-rows record`" in database_notes
    assert "fail before target rows are\ncopied" in database_notes
    assert "Focused unit tests use synthetic source and target schemas" in database_notes
    assert "Postgres\nsequence repair" in database_notes
    assert "Run the backup rehearsal procedure for end-to-end evidence" in database_notes
    assert "partial staging backup rehearsal completed with\n   sanitized reports" in database_notes
    assert "game-history rows and stats read paths" in database_notes
    assert "sparse-stats limitation is accepted for the current migration evidence" in (
        database_notes
    )
    assert "source that omits any required table is rejected by the importer" in (
        database_notes
    )
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
    assert "Every application table, including `rating` and `record`, must exist" in (
        backup_runbook
    )
    assert "source with empty stats tables\ncan still exercise" in backup_runbook
    assert "When the server never generated persisted stats" in backup_runbook
    assert "do not claim persisted rating or derived-record coverage" in (
        backup_runbook
    )
    assert "For a partial sparse-source rehearsal" in backup_runbook
    assert (
        "omit\n`--require-source-rows rating` and `--require-source-rows record`"
        in backup_runbook
    )
    assert "Record the empty stats tables in the\nrehearsal summary" in backup_runbook
    assert "A missing table remains a schema validation failure" in backup_runbook
    assert "Do not\nuse a partial sparse-source rehearsal as production cutover evidence" in (
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
    assert "acquire-validate-migration-reports" in backup_runbook
    assert "--dry-run-report /tmp/acquire-rehearsal/dry-run-report.json" in backup_runbook
    assert "--import-report /tmp/acquire-rehearsal/import-report.json" in backup_runbook
    assert "--require-source-rows rating" in backup_runbook
    assert "--require-source-rows record" in backup_runbook
    assert "sparse source dump that lacks\n   persisted rating history" in backup_runbook
    assert "separate disposable test database" in normalized_backup_runbook
    assert "Do not point the marker at the\n   imported Postgres target" in backup_runbook
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
    assert "docker compose run --rm python-gateway acquire-setup-database" in readme
    assert "docker compose run --rm python-gateway acquire-setup-database" in (
        local_development
    )
    assert "`acquire.setup_database`" in database_notes
    assert "server/setup_database.py" not in database_notes
    assert "The legacy MySQL reset command has been removed" in database_notes
    assert "python initialize_database.py" not in readme
    assert "python initialize_database.py" not in local_development
