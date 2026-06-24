# Postgres Backup Rehearsal Runbook

This runbook is for rehearsing a MySQL-to-Postgres migration with a sanitized
or staging MySQL backup. It is not a production cutover procedure. Use
disposable local databases and keep backup files outside the repository.

## Inputs

- Sanitized MySQL dump or staging backup stored outside the checkout, such as
  under `/tmp/acquire-rehearsal`.
- Disposable MySQL database restored from that backup.
- Disposable Postgres database with the current Alembic schema applied.
- Current branch with `server/import_mysql_to_postgres.py` and the Docker-backed
  marker suites passing.

Do not use a production backup that contains secrets or private user data unless
the file stays in an approved controlled environment. Do not commit dumps,
restored data, generated reports, database credentials, or local connection
strings to the repository.

## Rehearsal Steps

1. Create a working directory outside the repository for the backup, logs, and
   generated reports.
2. Restore the MySQL backup into a disposable MySQL database.
3. Create or reset a disposable Postgres database.
4. Apply Alembic migrations to the disposable Postgres database with an
   explicit placeholder connection override, replacing the URL with the
   rehearsal target:

   ```bash
   ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/acquire_rehearsal \
     uv run alembic upgrade head
   ```

5. Run `server/import_mysql_to_postgres.py` with explicit placeholder source and
   target URLs, `--dry-run`, and a report path outside the repository. Review
   the per-table source counts:

   ```bash
   uv run python server/import_mysql_to_postgres.py \
     --source-url mysql+mysqlconnector://user:password@host:3306/acquire_rehearsal \
     --target-url postgresql+psycopg://user:password@host:5432/acquire_rehearsal \
     --dry-run \
     --report-json /tmp/acquire-rehearsal/dry-run-report.json
   ```

6. Run the import without `--dry-run` only after the dry-run source counts match
   expectations and the non-lookup target tables are confirmed empty. Write a
   second report for the completed import:

   ```bash
   uv run python server/import_mysql_to_postgres.py \
     --source-url mysql+mysqlconnector://user:password@host:3306/acquire_rehearsal \
     --target-url postgresql+psycopg://user:password@host:5432/acquire_rehearsal \
     --report-json /tmp/acquire-rehearsal/import-report.json
   ```

   The JSON report contains only dry-run mode, total rows, table names, and
   source/target counts. It must not include connection URLs, credentials,
   hostnames, backup paths, or row contents.
7. Validate the report pair before using it as rehearsal evidence:

   ```bash
   uv run python server/validate_import_reports.py \
     --dry-run-report /tmp/acquire-rehearsal/dry-run-report.json \
     --import-report /tmp/acquire-rehearsal/import-report.json
   ```

   This check verifies that both reports use the sanitized report shape, that
   the dry-run and import source counts match, and that every imported target
   count equals its source count.
8. Run the MySQL and Postgres pytest marker suites as independent database
   compatibility checks. Keep these marker suites pointed at separate
   disposable test databases, or leave their test URLs unset so their fixtures
   create their own databases. Do not point marker test URLs at the restored
   MySQL source or imported Postgres target because those fixtures reset
   application tables.
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
- `server/validate_import_reports.py` accepts the dry-run/import report pair.
- Imported Postgres rows pass application-level checks through Python auth
  rules, ORM lookup helpers, completed-game rating checks, stats checks, and
  historical replay checks.
- Postgres primary-key sequences advance after explicit id imports.
- MySQL, Postgres, and e2e marker suites pass after the rehearsal.
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
