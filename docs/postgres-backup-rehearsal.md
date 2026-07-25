# Postgres Backup Rehearsal Runbook

This runbook is for rehearsing a MySQL-to-Postgres migration with a sanitized
or staging MySQL backup. It is not a production cutover procedure. Use
disposable local databases and keep backup files outside the repository.

## Inputs

- Sanitized MySQL dump or staging backup stored outside the checkout, such as
  under `/tmp/acquire-rehearsal`.
- Disposable MySQL database restored from that backup.
- Disposable Postgres database with the current Alembic schema applied.
- Current branch with `acquire.migration.import_mysql_to_postgres`, its focused unit
  tests, and the Postgres/e2e marker suites passing.

Do not use a production backup that contains secrets or private user data unless
the file stays in an approved controlled environment. Do not commit dumps,
restored data, generated reports, database credentials, or local connection
strings to the repository.

## Source Readiness Check

Before creating the backup for a production-like rehearsal, confirm that the
source contains the historical stats data required to validate the migration:

```sql
select 'rating' as table_name, count(*) as row_count from rating
union all
select 'record' as table_name, count(*) as row_count from record;
```

Every application table, including `rating` and `record`, must exist in the
restored source or the importer rejects it.

Both counts must be greater than zero for the rehearsal to prove persisted
rating history and derived win/place stats. A source with empty stats tables
can still exercise schema, user, game-history, and key/value import behavior.
When the server never generated persisted stats, record that limitation in the
rehearsal summary and do not claim persisted rating or derived-record coverage.

For a partial sparse-source rehearsal, follow the same restore, dry-run,
import, report-validation, and application-check steps, but omit
`--require-source-rows rating` and `--require-source-rows record` from the
import and report-validation commands. Record the empty stats tables in the
rehearsal summary. A missing table remains a schema validation failure. Do not
use a partial sparse-source rehearsal as production cutover evidence for
persisted rating history or derived win/place stats.

## Rehearsal Steps

1. Create a working directory outside the repository for the backup, logs, and
   generated reports.
2. Restore the MySQL backup into a disposable MySQL database. If the source
   readiness check was not run before the dump was created, run the same
   `rating` and `record` count check against the restored disposable source
   before creating the Postgres target.
3. Create or reset a disposable Postgres database.
4. Apply Alembic migrations to the disposable Postgres database with an
   explicit placeholder connection override, replacing the URL with the
   rehearsal target:

   ```bash
   ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/acquire_rehearsal \
     uv run alembic upgrade head
   ```

5. Run `acquire.migration.import_mysql_to_postgres` with explicit placeholder source and
   target URLs, `--dry-run`, and a report path outside the repository. Review
   the per-table source counts:

   ```bash
   uv run --extra mysql-migration python -m acquire.migration.import_mysql_to_postgres \
     --source-url mysql+mysqlconnector://user:password@host:3306/acquire_rehearsal \
     --target-url postgresql+psycopg://user:password@host:5432/acquire_rehearsal \
     --dry-run \
     --require-source-rows rating \
     --require-source-rows record \
     --report-json /tmp/acquire-rehearsal/dry-run-report.json
   ```

6. Run the import without `--dry-run` only after the dry-run source counts match
   expectations and the non-lookup target tables are confirmed empty. Write a
   second report for the completed import:

   ```bash
   uv run --extra mysql-migration python -m acquire.migration.import_mysql_to_postgres \
     --source-url mysql+mysqlconnector://user:password@host:3306/acquire_rehearsal \
     --target-url postgresql+psycopg://user:password@host:5432/acquire_rehearsal \
     --require-source-rows rating \
     --require-source-rows record \
     --report-json /tmp/acquire-rehearsal/import-report.json
   ```

   The JSON report contains only dry-run mode, total rows, table names, and
   source/target counts. It must not include connection URLs, credentials,
   hostnames, backup paths, or row contents.
   The required source-row checks fail before target rows are copied if the
   source dump lacks persisted rating history or derived win/place stats
   records.
7. Validate the report pair before using it as rehearsal evidence:

   ```bash
   uv run python -m acquire.migration.validate_import_reports \
     --dry-run-report /tmp/acquire-rehearsal/dry-run-report.json \
     --import-report /tmp/acquire-rehearsal/import-report.json \
     --require-source-rows rating \
     --require-source-rows record
   ```

   This check verifies that both reports use the sanitized report shape, that
   the dry-run and import source counts match, and that every imported target
   count equals its source count. The required source-row checks keep a
   production-like rehearsal from passing with a sparse source dump that lacks
   persisted rating history or derived win/place stats records.
8. Run the focused importer unit tests and the Postgres marker suite. Keep the
   Postgres marker pointed at a separate disposable test database, or leave its
   test URL unset so the fixture creates one. Do not point the marker at the
   imported Postgres target because the fixture resets application tables.
9. Start the local gateway against the imported Postgres database before running
   e2e checks as evidence for the imported data. The default Compose gateway
   points at the fresh `postgres` service, and the gateway requires generated
   client assets before it can serve the UI. Build the client assets first:

   ```bash
   docker compose --profile client-build run --rm client-assets
   ```

   For Linux Docker Engine, save this temporary Compose override outside the
   repository as `/tmp/acquire-rehearsal/gateway.override.yml` so
   `host.docker.internal` resolves from inside the gateway container:

   ```yaml
   services:
     python-gateway:
       extra_hosts:
         - "host.docker.internal:host-gateway"
   ```

   Then start a one-off gateway with an explicit imported-database URL and no
   service dependencies:

   ```bash
   docker compose -f docker-compose.yml -f /tmp/acquire-rehearsal/gateway.override.yml \
     run --rm --service-ports --no-deps \
     -e ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host.docker.internal:5432/acquire_rehearsal \
     python-gateway
   ```

   Replace the placeholder URL with a connection string that is reachable from
   inside the gateway container. Docker Desktop users may omit the temporary
   override if `host.docker.internal` already resolves. When validating
   imported-data behavior, point `ACQUIRE_E2E_URL` at this gateway. If
   `ACQUIRE_E2E_URL` is unset, the default Docker-backed e2e fixture creates a
   fresh database instead of using the imported rehearsal target.
10. Verify representative application behavior against the imported Postgres
   database: login, global chat, game creation, joining, starting, tile play,
   stats pages, and historical replay checks.
11. Record the sanitized rehearsal outcome in the project notes or PR summary
   without including credentials, host-specific paths, or private data.

## Pass Criteria

- The backup restore succeeds into a disposable MySQL database.
- Alembic creates the target Postgres schema at the expected head revision.
- The import dry-run JSON report records source row counts that match
  expectations while non-lookup target tables remain empty.
- The actual import JSON report matches source and target row counts for every
  copied table.
- `acquire.migration.validate_import_reports` accepts the dry-run/import report pair.
- Imported Postgres rows pass application-level checks through Python auth
  rules, ORM lookup helpers, stats checks, and historical replay checks.
- Completed-game rating checks pass when the source generated persisted rating
  rows; otherwise the rehearsal records the sparse-stats limitation.
- Postgres primary-key sequences advance after explicit id imports.
- Focused importer unit tests plus the Postgres and e2e marker suites pass after
  the rehearsal.
- The rollback owner confirms whether any post-cutover Postgres writes would be
  reconciled back to MySQL or deliberately discarded during rollback.

## Failure Handling

If any restore, import, validation, or marker test fails, stop the rehearsal and
keep the MySQL backup as the source of truth. Do not retry against the same
Postgres database after partial import; recreate the disposable target database
from scratch, rerun Alembic, and repeat the import after fixing the failure.

If the failure exposes missing schema compatibility, import-tool behavior, or
application validation coverage, add a focused test before repeating the
rehearsal.
