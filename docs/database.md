# Database Notes

Postgres is the application runtime database, and Alembic owns schema
migrations. MySQL is supported only as the source format for importing an
existing backup into Postgres.

## Current State

- Python database models live in the installed `acquire.orm` module.
- Alembic configuration and migrations live as installed resources under
  `src/acquire/`.
- The initial Alembic revision creates the current Postgres schema and required
  lookup rows.
- `acquire.setup_database` applies Alembic migrations for local Docker and e2e
  setup without dropping data. Local Docker, deployment, and installed
  environments invoke that boundary through `acquire-setup-database`.
- `acquire.migration.import_mysql_to_postgres` copies known application tables from a
  MySQL-compatible source into a migrated Postgres-compatible target for
  cutover rehearsals. It accepts matching Alembic-seeded lookup rows but refuses
  to merge user, game, rating, record, or key/value data into non-empty target
  tables. Focused unit tests cover command behavior against synthetic schemas,
  and the completed staging rehearsal provides evidence for the end-to-end
  backup workflow. The importer requires every application table, including
  the derived `record` table. The optional `--require-source-rows` checks
  require selected tables to be nonempty for production-like rehearsals because
  runtime stats reads do not rebuild historical win/place records from
  imported games.
- The legacy MySQL reset command has been removed. Alembic and
  `acquire.setup_database` are the supported schema setup paths.
- Postgres marker tests cover connectivity, ORM metadata creation, the Alembic
  baseline, transaction behavior, auth persistence, runtime constraints,
  lookup persistence, and completed-game log import persistence.

## Retained MySQL Backup Surface

- `acquire.migration.import_mysql_to_postgres` and
  `acquire.migration.validate_import_reports` retain the backup import and sanitized
  report-validation workflow. Separate migration-owned metadata defines the
  supported legacy MySQL source and current Postgres target contracts without
  importing the runtime ORM or creating its global engine.
- The `mysql-migration` optional uv extra installs
  `mysql-connector-python`; normal development and production runtime
  dependencies do not install a MySQL driver.
- `acquire.orm` uses `ACQUIRE_DATABASE_URL` or structured `POSTGRES_*`
  environment variables for application connections. It has no MySQL runtime
  fallback.
- `src/acquire/migrations/versions/20260622_0001_baseline_mysql_schema.py` uses portable
  SQLAlchemy types and preserves the historical source schema contract needed
  to interpret legacy backups. It is not an application runtime connection
  path.
- Docker Compose, CI marker suites, and local development are Postgres-only.

## Installed Database Setup Command

Configure the target with `ACQUIRE_DATABASE_URL` or the structured
`POSTGRES_*` environment variables used by `acquire.orm`, then run:

```bash
uv run acquire-setup-database
```

The command discovers its Alembic configuration and revisions through installed
package resources. It accepts no operational arguments: `--help` exits with
status 0 without connecting to a database, unexpected arguments exit with
status 2, successful fresh, guarded-legacy, already-versioned, and repeated
setups exit with status 0, and resource, inspection, connection, or migration
failures exit with status 1.

Direct Alembic CLI invocation from the repository root is unsupported. The
repository has no root `alembic.ini`; use `acquire-setup-database` for schema
setup and the packaged resource boundary for migration tests.

| Field | Source and trust | Runtime use | Diagnostic policy |
| --- | --- | --- | --- |
| Database URL and structured connection settings | Operator environment, sensitive | Construct the application engine used for inspection and migrations | Never print or serialize |
| Command arguments | Operator input, untrusted and unsupported except `--help` | Validate that no operational arguments were supplied | Reject with a fixed marker; never reflect input |
| Packaged Alembic paths | Installed package metadata, trusted | Load configuration and revision scripts | Exclude paths from failure output |
| Database and migration exceptions | Driver, SQLAlchemy, or Alembic, potentially sensitive | Determine failure status | Replace with the fixed `error: database setup failed` marker |

## Postgres Migration Sequence

1. Add Postgres test dependencies and Docker Compose services while leaving
   MySQL as the default runtime. Complete.
2. Add a `postgres` pytest marker and Docker-backed fixture that can create a
   disposable Postgres schema for integration tests. Complete.
3. Make ORM URL construction engine-neutral, using explicit database URLs for
   tests and local services while preserving the existing MySQL environment
   behavior during the transition. Complete for the current migration baseline.
4. Add a Postgres baseline migration path or revise the baseline to use
   portable SQLAlchemy types where possible, with explicit treatment for
   binary/case-sensitive username semantics. Complete for the current
   migration baseline.
5. Run schema, lookup, auth, session, and log-import persistence tests against
   both MySQL and Postgres until parity is proven. Complete for the current
   migration baseline.
6. Replace `initialize_database.py` with Alembic upgrade plus seed data in
   local Docker and e2e setup. Complete. The legacy reset command has been
   removed.
7. Switch local development defaults from MySQL to Postgres after the dual
   database test suite is green. Complete.
8. Document the production deployment and rollback gate before removing MySQL
   runtime paths. Complete.
9. Add tested MySQL-to-Postgres import tooling for cutover rehearsals.
   Complete for synthetic unit coverage and Docker-backed MySQL-to-Postgres
   rehearsal coverage. A partial staging backup rehearsal completed with
   sanitized reports covering lookup, user, game, game-player, and key/value
   rows from a legacy source whose required `rating` and `record` tables were
   empty because that server did not generate persisted stats. This
   sparse-stats limitation is accepted for the current migration evidence; a
   source that omits any required table is rejected by the importer.
10. Remove MySQL-only runtime dependencies, Compose services, environment
    variables, marker tests, and runtime documentation. Complete. The backup
    importer remains available through the `mysql-migration` optional extra.

## Import Rehearsal Command

Use `acquire-migrate-mysql-to-postgres` only with disposable rehearsal databases
until the production runbook has owners and a tested backup restore. The target
database must already have the current Alembic schema applied:

```bash
uv run --extra mysql-migration acquire-migrate-mysql-to-postgres \
  --source-url mysql+mysqlconnector://user:password@host/source_db \
  --target-url postgresql+psycopg://user:password@host/target_db \
  --dry-run
```

Remove `--dry-run` only after the count report and target validation look
correct. The command copies the known application tables in foreign-key-safe
order, preserves primary keys, and reports source and target row counts for
each table. Baseline lookup tables may already contain Alembic-seeded rows when
they exactly match the source. Other target tables must be empty. Use
`--require-source-rows rating --require-source-rows record` for
production-like rehearsals so sparse source dumps fail before target rows are
copied.

Focused unit tests use synthetic source and target schemas to protect table
validation, target safeguards, row copying, report output, and Postgres
sequence repair. Run the backup rehearsal procedure for end-to-end evidence
against a restored MySQL backup.

### Migration Data Boundary

| Field | Source and trust | Runtime use | Diagnostic policy |
| --- | --- | --- | --- |
| Source and target URLs | Operator-supplied, sensitive | Create short-lived migration engines | Never serialize or print |
| Source rows | Legacy backup, private and untrusted | Validate and copy known columns only | Never include values or row representations |
| Report path | Operator-supplied local path | Preflight and write the report file | Never include in report JSON |
| Report mode, table names, and counts | Importer-generated, non-sensitive | Rehearsal evidence and pair validation | Preserve in the fixed sanitized schema |

Report validation rejects unknown and duplicate fields so encoded URLs,
credentials, paths, hostnames, or row contents cannot become accepted output.

Validate a dry-run/import report pair with the normal installation:

```bash
uv run acquire-validate-migration-reports \
  --dry-run-report /absolute/path/dry-run-report.json \
  --import-report /absolute/path/import-report.json
```

The importer exits with `2` for invalid arguments, `3` for an unsafe target,
`4` when the optional MySQL source driver is unavailable, `5` for an import
failure, and `6` for a report-write failure. The validator exits with `2` for
invalid arguments and `7` for report or validation failures. Both commands use
fixed single-line diagnostics: connection values, credentials, hostnames,
private paths, row contents, and exception representations are never projected
to stdout or stderr.

Use `docs/postgres-backup-rehearsal.md` when repeating the rehearsal with a new
sanitized or staging MySQL backup. The runbook keeps backup files, credentials,
generated reports, host-specific paths, and private data out of the repository
and defines the pass/fail criteria for counting the rehearsal as complete. It
also includes a source readiness check for nonzero `rating` and `record` table
counts when a source claims to contain persisted stats.

## Backup Import And Deployment Gate

The application runtime is Postgres-only. Importing an existing MySQL backup
still requires an explicit deployment plan, owners, and a tested dry run.

### Cutover Preconditions

- A fresh MySQL backup exists and restore has been tested outside production.
- The target Postgres database starts from an empty schema created with
  `acquire-setup-database`.
- A repeatable export/import command exists for production data, including
  users, games, actions, chat messages, and game-player rows.
- The import dry run validates row counts, representative user login behavior,
  historical game replay checks, and completed-game ratings when the source
  generated persisted rating rows.
- The focused importer unit tests, Postgres marker suite, and e2e suite pass.
- The deployment owner has selected a maintenance window and a rollback owner.

### Deployment Plan

1. Put the production application in maintenance mode or otherwise stop writes.
2. Take and verify a final MySQL backup.
3. Provision Postgres and run Alembic migrations to the expected head revision.
4. Import MySQL data into Postgres with the repeatable import command.
5. Validate imported data with row-count checks, login checks, persisted-game
   checks, and representative historical replay checks.
6. Deploy the Python gateway configured with the Postgres connection.
7. Run smoke checks for login, global chat, game creation, joining, starting,
   tile play, and stats pages before reopening traffic.

### Rollback Plan

Rollback is only straightforward while production writes remain stopped or
while the Postgres deployment is still inside the validation window. If
validation fails before reopening traffic, discard the Postgres target and
continue operating the source system without deploying this Postgres-only
application version.

If traffic has already been reopened and Postgres has accepted writes, rollback
requires an explicit data-reconciliation decision. The project does not
dual-write, and this repository no longer provides a MySQL application runtime.

### Retained Migration Rules

- Keep the MySQL-to-Postgres backup import tool and its optional driver extra
  until migration from existing MySQL backups is no longer required.
- Keep Alembic and `acquire.setup_database` as the only schema setup paths.
- Do not add MySQL connection settings, Compose services, marker fixtures, or
  drivers back to the normal application runtime.

## Current Limitations

- The Postgres runtime uses `psycopg` 3.
- The production import command has been validated against the available
  staging backup rehearsal for game-history rows and stats read paths. The
  staging source contained the required `rating` and `record` tables but no
  rows in either, so persisted rating/record evidence is explicitly unavailable
  for the current server. A future backup import still requires a fresh backup,
  a selected maintenance window, and final pre-deployment validation.
- The backup rehearsal runbook is documented in
  `docs/postgres-backup-rehearsal.md`; repeat it for any newer staging or
  production-like backup before deployment.
- The deployment and rollback owners must be selected before importing a
  production backup.
