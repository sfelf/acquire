# Database Notes

MySQL is the current database. Alembic now owns schema migrations, and the next
database modernization goal is moving to Postgres without losing the MySQL
persistence coverage that protects the refactor.

## Current State

- Python database models live in `server/orm.py`.
- Alembic migrations live in `migrations/`.
- The initial Alembic revision creates the current MySQL schema and required
  lookup rows.
- `server/initialize_database.py` still provides a local reset path while the
  Compose workflows are migrated to Alembic-owned setup.
- MySQL integration tests cover schema creation, migrations, runtime
  constraints, auth persistence, lookup persistence, transaction behavior, and
  completed-game log import persistence.

## MySQL-Specific Surface Area

- `server/orm.py` imports MySQL dialect column types and builds a
  `mysql+mysqlconnector` URL from `MYSQL_*` environment variables.
- `server/initialize_database.py` shells out to the `mysql` CLI, recreates the
  schema with `utf8mb4_bin`, and seeds lookup rows.
- `migrations/versions/20260622_0001_baseline_mysql_schema.py` uses MySQL
  dialect types and MySQL table collation options to match the current schema.
- `server/cron.py`, `server/recreate_game.py`, and `server/logs_to_games.py`
  use raw SQL that must be reviewed for cross-database behavior before the
  runtime switches engines.
- Docker Compose, test fixtures, and local-development docs currently start
  MySQL services and expose MySQL-specific test URLs.

## Postgres Migration Sequence

1. Add Postgres dev/runtime dependencies and Docker Compose services while
   leaving MySQL as the default runtime.
2. Add a `postgres` pytest marker and Docker-backed fixture that can create a
   disposable Postgres schema for integration tests.
3. Make ORM URL construction engine-neutral, using explicit database URLs for
   tests and local services while preserving the existing MySQL environment
   behavior during the transition.
4. Add a Postgres baseline migration path or revise the baseline to use
   portable SQLAlchemy types where possible, with explicit treatment for
   binary/case-sensitive username semantics.
5. Run schema, lookup, auth, session, and log-import persistence tests against
   both MySQL and Postgres until parity is proven.
6. Replace `initialize_database.py` with Alembic upgrade plus seed data in
   local Docker and e2e setup, then remove the legacy reset command.
7. Switch local development defaults from MySQL to Postgres after the dual
   database test suite is green.
8. Remove MySQL-only dependencies, Compose services, environment variables, and
   documentation after deployment and rollback plans are documented.

## Open Decisions

- Choose the Postgres driver. `psycopg` 3 is the preferred modern default
  unless compatibility testing shows a reason to use `psycopg2`.
- Decide whether production migration starts from an empty Postgres schema plus
  imported data or from a direct MySQL-to-Postgres data transfer.
- Define the production rollback strategy before making Postgres the default
  deployment database.
