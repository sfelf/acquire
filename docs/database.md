# Database Notes

MySQL is the current database. Alembic now owns schema migrations, and the next
database modernization goal is moving to Postgres without losing the MySQL
persistence coverage that protects the refactor.

## Current State

- Python database models live in `server/orm.py`.
- Alembic migrations live in `migrations/`.
- The initial Alembic revision creates the current schema and required lookup
  rows against MySQL and Postgres.
- `server/setup_database.py` applies Alembic migrations for local Docker and
  e2e setup without dropping data.
- `server/initialize_database.py` remains as a legacy local reset path until
  MySQL rollback and reset workflows are replaced.
- MySQL integration tests cover schema creation, migrations, runtime
  constraints, auth persistence, lookup persistence, transaction behavior, and
  completed-game log import persistence. Postgres marker tests now cover
  connectivity, ORM metadata creation, the Alembic baseline, transaction
  behavior, auth persistence, runtime constraints, lookup persistence, and
  completed-game log import persistence.

## MySQL-Specific Surface Area

- `server/orm.py` keeps MySQL as the default runtime URL from `MYSQL_*`
  environment variables, but can use an explicit `ACQUIRE_DATABASE_URL` for
  Postgres testing and migration work.
- `server/initialize_database.py` shells out to the `mysql` CLI, recreates the
  schema with `utf8mb4_bin`, and seeds lookup rows for the legacy reset path.
- `migrations/versions/20260622_0001_baseline_mysql_schema.py` uses portable
  SQLAlchemy types with MySQL variants and applies MySQL table collation
  options only when running against MySQL.
- `server/cron.py` uses dialect-aware SQL rendering for stats queries that
  reference the legacy `user` table, and computes the rolling ratings cutoff in
  Python so the stats query no longer depends on MySQL timestamp functions.
- Remaining raw SQL in `server/recreate_game.py` and `server/logs_to_games.py`
  must still be reviewed for cross-database behavior before the runtime
  switches engines.
- Docker Compose, test fixtures, and local-development docs currently start
  MySQL services and expose MySQL-specific test URLs.

## Postgres Migration Sequence

1. Add Postgres test dependencies and Docker Compose services while leaving
   MySQL as the default runtime. Complete.
2. Add a `postgres` pytest marker and Docker-backed fixture that can create a
   disposable Postgres schema for integration tests. Complete.
3. Make ORM URL construction engine-neutral, using explicit database URLs for
   tests and local services while preserving the existing MySQL environment
   behavior during the transition. In progress.
4. Add a Postgres baseline migration path or revise the baseline to use
   portable SQLAlchemy types where possible, with explicit treatment for
   binary/case-sensitive username semantics. In progress.
5. Run schema, lookup, auth, session, and log-import persistence tests against
   both MySQL and Postgres until parity is proven. Complete for the current
   migration baseline.
6. Replace `initialize_database.py` with Alembic upgrade plus seed data in
   local Docker and e2e setup. Complete. Remove the legacy reset command after
   the MySQL rollback workflow is documented.
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
