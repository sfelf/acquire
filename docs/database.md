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
- `server/initialize_database.py` remains as a legacy local reset path until
  MySQL rollback and reset workflows are replaced.
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
- `server/initialize_database.py` shells out to the `mysql` CLI, recreates the
  schema with `utf8mb4_bin`, and seeds lookup rows for the legacy reset path.
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
   local Docker and e2e setup. Complete. Remove the legacy reset command after
   the MySQL rollback workflow is documented.
7. Switch local development defaults from MySQL to Postgres after the dual
   database test suite is green. Complete.
8. Remove MySQL-only dependencies, Compose services, environment variables, and
   documentation after deployment and rollback plans are documented.

## Open Decisions

- Postgres driver selection is complete for the current migration baseline:
  `psycopg` 3 is used for Docker-backed marker tests.
- Decide whether production migration starts from an empty Postgres schema plus
  imported data or from a direct MySQL-to-Postgres data transfer.
- Define the production rollback strategy before making Postgres the default
  deployment database.
