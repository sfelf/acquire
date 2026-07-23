# Database Notes

Postgres is the default local Docker database. Alembic owns schema migrations,
and the database modernization goal remains moving toward Postgres without
losing the MySQL persistence coverage that protects the refactor.

## Current State

- Python database models live in `server/orm.py`.
- Alembic migrations live in `migrations/`.
- The initial Alembic revision creates the current schema and required lookup
  rows against MySQL and Postgres.
- `server/setup_database.py` applies Alembic migrations for local Docker and
  e2e setup without dropping data. Local Docker now runs this against
  Postgres by default.
- `server/import_mysql_to_postgres.py` copies known application tables from a
  MySQL-compatible source into a migrated Postgres-compatible target for
  cutover rehearsals. It accepts matching Alembic-seeded lookup rows but refuses
  to merge user, game, rating, record, or key/value data into non-empty target
  tables. Unit tests cover command behavior against synthetic schemas, and the
  Postgres marker suite runs a Docker-backed rehearsal from MySQL into
  Postgres. The importer can require the derived `record` table for sources
  that generated historical stats because runtime stats reads do not rebuild
  historical win/place records from imported games.
- The legacy MySQL reset command has been removed. Alembic and
  `server/setup_database.py` are the supported schema setup paths.
- MySQL integration tests cover schema creation, migrations, runtime
  constraints, auth persistence, lookup persistence, transaction behavior, and
  completed-game log import persistence. Postgres marker tests now cover
  connectivity, ORM metadata creation, the Alembic baseline, transaction
  behavior, auth persistence, runtime constraints, lookup persistence, and
  completed-game log import persistence.

## MySQL-Specific Surface Area

- `server/orm.py` uses explicit `ACQUIRE_DATABASE_URL` when present, structured
  `POSTGRES_*` environment variables for the local Docker Postgres path, and
  keeps the legacy `MYSQL_*` fallback for MySQL parity and rollback work.
- `migrations/versions/20260622_0001_baseline_mysql_schema.py` uses portable
  SQLAlchemy types with MySQL variants and applies MySQL table collation
  options only when running against MySQL.
- `server/cron.py` uses dialect-aware SQL rendering for stats queries that
  reference the legacy `user` table, and computes the rolling ratings cutoff in
  Python so the stats query no longer depends on MySQL timestamp functions.
- `server/logs_to_games.py` uses dialect-aware SQL rendering for manual
  database comparison tools that reference the legacy `user` table.
- `server/recreate_game.py` uses ORM lookups for persisted-game checks instead
  of raw SQL.
- Docker Compose and local-development docs use Postgres for the default local
  gateway stack. MySQL remains available as a Compose service for marker tests
  and parity coverage.

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
   rows from a legacy source that did not include rating rows or the derived
   `record` table because that server did not generate persisted stats. This
   sparse-stats limitation is accepted for the current migration evidence.
10. Remove MySQL-only dependencies, Compose services, environment variables, and
   documentation after the production cutover work has an approved execution
   plan and rollback owner. Retain the MySQL-to-Postgres backup import tool and
   the MySQL driver dependency until backups from the existing MySQL server no
   longer need to be migrated.

## Import Rehearsal Command

Use `server/import_mysql_to_postgres.py` only with disposable rehearsal
databases until the production runbook has owners and a tested backup restore.
The target database must already have the current Alembic schema applied:

```bash
uv run python server/import_mysql_to_postgres.py \
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

The `postgres` marker suite includes a Docker-backed rehearsal that creates
matching MySQL and Postgres schemas with Alembic, seeds representative MySQL
rows, imports them into Postgres, verifies key rows, and confirms Postgres
primary-key sequences advance after explicit id imports. The same rehearsal
also verifies the imported Postgres rows through the Python auth rules and ORM
lookup helpers.

Use `docs/postgres-backup-rehearsal.md` when repeating the rehearsal with a new
sanitized or staging MySQL backup. The runbook keeps backup files, credentials,
generated reports, host-specific paths, and private data out of the repository
and defines the pass/fail criteria for counting the rehearsal as complete. It
also includes a source readiness check for nonzero `rating` and `record` table
counts when a source claims to contain persisted stats.

## Production Cutover And Rollback Gate

Postgres is the default local Docker database, but production migration remains
gated on an explicit cutover runbook. Do not remove the MySQL rollback surface
needed by production until the following items have owners and a tested dry run.

### Cutover Preconditions

- A fresh MySQL backup exists and restore has been tested outside production.
- The target Postgres database starts from an empty schema created with
  `alembic upgrade head`.
- A repeatable export/import command exists for production data, including
  users, games, actions, chat messages, and game-player rows.
- The import dry run validates row counts, representative user login behavior,
  historical game replay checks, and completed-game ratings when the source
  generated persisted rating rows.
- The MySQL and Postgres marker suites pass against disposable schemas, and the
  e2e suite passes against the Postgres-backed local gateway.
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
while the Postgres cutover is still inside the validation window. If validation
fails before reopening traffic, point the application back at the verified
MySQL backup or the untouched MySQL primary, redeploy the previous
configuration, and rerun login plus gameplay smoke checks.

If traffic has already been reopened and Postgres has accepted writes, rollback
requires an explicit data-reconciliation decision before switching back to
MySQL. The project does not currently dual-write to both databases, so any
post-cutover Postgres writes must either be exported back to MySQL with a
reviewed script or deliberately discarded by the rollback owner.

### Runtime Cleanup Rules

- Keep MySQL marker tests until production no longer needs database parity or
  rollback confidence from the legacy engine.
- Keep the MySQL Compose profile until production rollback no longer depends on
  quickly starting a local MySQL parity stack.
- Keep the MySQL-to-Postgres backup import tool and MySQL driver dependency
  until migration from an existing MySQL server backup is no longer required.
- Keep Alembic and `server/setup_database.py` as the only schema setup paths.
- Remove the legacy `MYSQL_*` ORM fallback only after production deployment no
  longer needs the application to connect to MySQL during rollback.

## Open Decisions

- Postgres driver selection is complete for the current migration baseline:
  `psycopg` 3 is used for Docker-backed marker tests.
- The production import command has been validated against the available
  staging backup rehearsal for game-history rows and stats read paths. The
  staging source did not generate rating rows or the derived `record` table, so
  persisted rating/record evidence is explicitly unavailable for the current
  server. Production cutover still requires a fresh backup, a selected
  maintenance window, and final pre-cutover validation.
- The backup rehearsal runbook is documented in
  `docs/postgres-backup-rehearsal.md`; repeat it for any newer staging or
  production-like backup before cutover.
- The rollback owner and maintenance window must be selected before production
  deployment.
