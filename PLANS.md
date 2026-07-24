# Modernization And Packaging Plan

Status:

- The six-phase modernization plan is complete as of July 23, 2026.
- The Packaging milestone is active.

This document preserves the agreed modernization record and documents the
delivery order for active milestone work. GitHub issues remain the source of
truth for issue scope and acceptance criteria.

## Active Packaging Milestone

Status: ready to start with
[#103](https://github.com/sfelf/acquire/issues/103).

Goal: package the Python backend for uv-managed installation, normalize imports,
and expose stable project scripts without changing application behavior.

### Decisions

- Use `uv_build` with a bounded compatible version as the build backend. Acquire
  is a pure-Python, uv-managed application moving to the backend's conventional
  `src/acquire/` layout and does not require native extensions or custom build
  hooks.
- Preserve the dependency boundary already present on `main`: SQLAlchemy and
  Psycopg are normal runtime dependencies, while `mysql-connector-python`
  remains isolated in the `mysql-migration` optional extra. Packaging work
  verifies this boundary rather than introducing it.
- Wheels contain only installable runtime modules, declared package data,
  metadata, and entry points. They exclude tests and test fixtures.
- Source distributions also contain the tracked test suite and its required
  sanitized fixtures. They exclude generated assets, credentials, database
  dumps, sockets, caches, bytecode, coverage output, and temporary reports.
- Temporary `server/` compatibility wrappers may exist only while callers are
  being migrated. They contain no application logic, identify
  [#111](https://github.com/sfelf/acquire/issues/111) as their removal owner,
  and are not a second supported API.

### Dependency Waves

Issues may be worked in the following dependency waves:

1. Package foundation:
   [#103](https://github.com/sfelf/acquire/issues/103) adds the installable
   `src/acquire/` scaffold and `uv_build` configuration without moving
   production modules.
2. Foundational modules:
   [#104](https://github.com/sfelf/acquire/issues/104) moves settings, enums,
   utilities, and username lookup after #103.
3. Persistence boundary:
   [#105](https://github.com/sfelf/acquire/issues/105) moves ORM,
   authentication, and database setup after #103 and #104.
4. Two tracks become independently available after #105:
   - Runtime and maintenance track:
     [#106](https://github.com/sfelf/acquire/issues/106) moves the game and
     realtime HTTP runtime, then
     [#107](https://github.com/sfelf/acquire/issues/107) moves replay, stats,
     and maintenance tooling.
   - Backup migration track:
     [#108](https://github.com/sfelf/acquire/issues/108) isolates the
     MySQL-to-Postgres importer, then
     [#109](https://github.com/sfelf/acquire/issues/109) adds its installed
     project script while preserving the existing optional extra.
5. Routine application commands:
   [#110](https://github.com/sfelf/acquire/issues/110) follows #105, #106, and
   #107. Coordinate it after #109 when working serially so project-script names,
   package metadata, the lock file, and command documentation are reconciled
   once.
6. Package closeout:
   [#111](https://github.com/sfelf/acquire/issues/111) follows #104 through
   #110, removes all transitional wrappers and path assumptions, verifies
   artifact contents, and records the final package and entry-point inventory.

The recommended serial merge order is:

1. #103
2. #104
3. #105
4. #106
5. #107
6. #108
7. #109
8. #110
9. #111

The serial order is preferred for one-agent delivery because it keeps each
change reviewable and minimizes conflicts in package configuration, imports,
tests, CI, Docker, and documentation. Parallel delivery may use the two tracks
in wave 4, but each issue must still satisfy its declared dependencies before
merge.

### Issue Verification Gates

| Issue | Completion evidence |
| --- | --- |
| [#103](https://github.com/sfelf/acquire/issues/103) | Editable install, `uv_build` wheel and source distribution, import smoke test outside the repository, supported-Python CI coverage, and unchanged runtime validation. |
| [#104](https://github.com/sfelf/acquire/issues/104) | Installed foundational imports, focused behavior tests, equivalent enum generation, and documented transitional wrappers. |
| [#105](https://github.com/sfelf/acquire/issues/105) | Installed persistence/auth imports, working Alembic upgrade from another working directory, idempotent setup, preserved dependency isolation, and Postgres/auth regression coverage. |
| [#106](https://github.com/sfelf/acquire/issues/106) | Installed FastAPI and game-runtime imports, explicit static-asset paths, and unchanged HTTP, WebSocket, protocol, integration, and e2e behavior. |
| [#107](https://github.com/sfelf/acquire/issues/107) | Installed offline-tool imports, golden replay equivalence, preserved stats/rating/persistence behavior, and path-sensitive coverage outside `server/`. |
| [#108](https://github.com/sfelf/acquire/issues/108) | Importer loading without a global runtime engine, an explicit legacy-source/current-target schema boundary, preserved rehearsal behavior, failure-path coverage, and sanitized reports. |
| [#109](https://github.com/sfelf/acquire/issues/109) | Installed migration command, normal-sync/optional-extra isolation checks, command-level error and redaction tests, and a successful Docker-backed rehearsal. |
| [#110](https://github.com/sfelf/acquire/issues/110) | Installed gateway and database-setup commands, Docker and enum-generation parity, command parsing tests, and Postgres/integration/e2e validation. |
| [#111](https://github.com/sfelf/acquire/issues/111) | No legacy import shims or `server/` path injection, asserted wheel/sdist manifests, a wheel built from the sdist, clean-environment command smoke tests, complete repository validation, and current documentation. |

Every issue must map its acceptance criteria to executable tests or explicit
verification in its pull request. Before merge, run the repository-required
formatting, lint, typing, test, pre-commit, and issue-specific package, Docker,
database, integration, golden, or e2e checks. Runtime behavior, public
protocols, persistence semantics, log formats, ratings, reports, and retained
backup-migration behavior remain unchanged throughout this milestone.

## Completed Modernization Goal

The project modernized the repository in phases so the team can safely perform
a major refactor, retire the Node.js server, keep the Python backend, preserve
current behavior through extensive pytest coverage, migrate from MySQL to
Postgres, support Docker-based development, and establish a production image
and optional AWS publishing path.

## Phase 1: Tooling And Agent Docs

Status: complete.

Scope:

- Add `uv` project metadata and lockfile.
- Add lenient `ruff` configuration.
- Add lenient `mypy` configuration.
- Add `pytest` as the test runner.
- Add `pre-commit` hooks for `ruff` and `mypy`.
- Add GitHub Actions CI for Python 3.12, 3.13, and 3.14.
- Add Codex-oriented project instructions.
- Add initial modernization docs and ADRs.

Constraints:

- Do not change runtime behavior.
- Do not migrate tests yet.
- Do not upgrade legacy runtime dependencies unless strictly required for tooling.
- Do not add Docker implementation yet.
- Do not begin Node.js deprecation yet.

## Phase 2: Test Foundation

Status: complete.

- Create a dedicated `tests/` layout. Complete.
- Move or mirror the existing `server/test.py` coverage under pytest. Complete.
- Add fixtures for game-server behavior. Complete.
- Add markers for `unit`, `integration`, `golden`, `mysql`, and `e2e`.
  Complete for the migration baseline; the MySQL marker was retired after the
  Postgres cutover.
- Add coverage reporting with a 90% minimum threshold. Complete.
- Keep fast tests separate from MySQL and end-to-end tests. Complete.

Notes:

- The pytest suite now covers the core Python server modules, log parser/processor helpers, ORM helpers, cron helpers, and replay fixtures without requiring MySQL for fast checks.
- Coverage now has a 90% minimum threshold across the measured Python source without legacy-function exclusions.
- Docker-backed Postgres and e2e marker fixtures are in place. Historical MySQL
  parity coverage was retired after Postgres became the sole runtime database.
  Integration coverage exercises Python server protocol flows for connection,
  chat, game creation, joining, starting, watching, leaving, disconnecting, and
  rejoining. E2E coverage verifies UI/report endpoints, login, global/game chat,
  game creation, joining, starting, tile play, watching, leaving, and rejoining
  through the local browser gateway.

## Phase 3: Golden Replay Tests

Status: complete.

- Use historical game logs as replay fixtures. Complete for the current refactor safety baseline.
- Add a replay harness for current game behavior. Complete for parser-level replay, individual-game extraction, and `LogProcessor` replay summaries.
- Store expected outputs or final states as golden files. Complete for the current refactor safety baseline.
- Document how to add new replay fixtures. Complete.
- Use replay tests as the main safety net for the major refactor. Complete for the current refactor safety baseline.

Notes:

- Add MySQL-backed integration coverage for schema creation, seed data, and persistence behavior. Complete for the current refactor safety baseline; expand when refactor work changes persistence behavior.
- Add fuller integration and e2e coverage around the Python gateway. Complete for the current refactor safety baseline; add targeted cases if refactor work uncovers additional gateway behavior.
- Historical fixtures include synthetic parser coverage and a representative redacted real-server fixture with summary, replay, final-state, and replay-to-server sync golden assertions.
- Future historical fixtures can still be added when new edge cases are discovered during refactor work, but they are no longer blocking Phase 3 completion.

## Phase 4: Local Development Docker

Status: complete.

- Add Docker Compose for local development. Complete.
- Include MySQL as a local service during migration. Complete and later retired
  after Postgres became the sole runtime database.
- Support the Python gateway while the Node.js backend runtime is retired. Complete.
- Expose the local browser UI through the Python gateway. Complete.
- Generate legacy client assets inside the local Docker profile. Complete.
- Add `.env.example`. Complete.
- Document local setup, UI access, and teardown commands. Complete.

## Phase 5: Python Backend Consolidation

Status: complete.

Phase 5 was completed as a sequence of focused PRs so each runtime boundary
change could be reviewed and validated independently.

1. Runtime boundary inventory. Complete. Document every Node-owned HTTP endpoint and
   SockJS message path, map each behavior to the existing Python equivalent or a
   missing Python implementation, and add any missing characterization tests
   before changing runtime code.
2. Move Node-owned HTTP endpoints to Python. Complete. Implement Python equivalents for
   non-websocket HTTP routes formerly served by `server/server.js` and prove
   existing browser flows still work through integration and e2e coverage.
3. Move auth and user checks fully into Python. Complete. Consolidate login,
   session, and user lookup behavior in the Python backend, with database-backed
   coverage for successful credentials, failed credentials, missing users,
   existing users, and session edge cases. Password setup is Python-owned;
   SockJS login has moved onto the Python gateway path for the default local
   runtime.
4. Add a Python websocket or SockJS-compatible gateway path. Complete.
   Introduce FastAPI as the Python HTTP framework first, then preserve the
   existing client protocol and add parity tests for representative workflows.
5. Switch local development and e2e tests to the Python gateway by default.
   Complete.
   Update Docker Compose, local development docs, and e2e defaults to use the
   Python gateway.
6. Remove Node.js from the main runtime path. Complete.
   Remove the Node gateway from the default local runtime, separate legacy
   client asset generation from the running Python gateway stack, and update
   agent/project docs to reflect Python as the primary backend.
7. Cleanup follow-up. Complete.
   Delete dead Node server code now that the Python path owns local HTTP,
   SockJS, auth, and gameplay workflows; remove obsolete docs, scripts, and
   dependency references; and tighten CI around the Python-only runtime path.

## Phase 6: Dependency And Deployment Modernization

Status: complete.

Phase 6 was split into small PRs so dependency risk, database migration risk,
frontend build changes, and deployment changes could be reviewed independently.

1. Upgrade Python runtime dependencies in controlled groups, starting with
   compatibility patches needed for supported Python versions. Complete.
2. Upgrade SQLAlchemy and add focused ORM/session regression coverage for any
   behavior that changes during the upgrade. Complete.
3. Add Alembic migrations for the current MySQL schema before changing database
   engines. Complete.
4. Plan and execute the MySQL-to-Postgres migration after migrations and
   persistence tests are in place. Complete.
   - Document the current MySQL-specific surface area and migration sequence.
     Complete.
   - Add Postgres dependencies and Docker-backed `postgres` marker fixtures
     alongside existing MySQL tests. Complete.
   - Make ORM models, migrations, and raw SQL portable while keeping MySQL
     tests green. Complete for the current migration baseline.
   - Run the persistence suite against both MySQL and Postgres during the
     transition. Complete for schema, session, auth, constraints, lookup, and
     completed-game log import coverage.
   - Replace `initialize_database.py` with Alembic upgrade plus seed data in
     local Docker and e2e setup. Complete.
   - Switch local development defaults to Postgres after parity is proven.
     Complete.
   - Document the production deployment and rollback gate for removing
     MySQL-only runtime paths. Complete.
   - Add tested MySQL-to-Postgres import tooling for cutover rehearsals.
     Complete for synthetic unit coverage and Docker-backed MySQL-to-Postgres
     rehearsal coverage. The Docker-backed rehearsal exercises sanitized JSON
     dry-run/import report generation and validation using the same workflow
     documented for real backup rehearsal evidence.
   - Document the sanitized or staging backup rehearsal runbook. Complete.
   - Run the import rehearsal against a sanitized or staging MySQL backup.
     Complete with an accepted sparse-stats limitation. The available staging
     source did not contain rating or derived `record` rows, so a fuller
     persisted rating/record rehearsal is not possible from the current server
     backup. The restored source still included every table required by the
     importer. The completed rehearsal proved lookup, user, game-history, and
     key/value import/report validation for 61 sanitized report rows and
     verified stats reads plus the gateway e2e suite against the imported
     Postgres target. The report validator and import command retain
     `--require-source-rows` for future sources that do contain persisted stats.
   - Remove MySQL-only runtime paths after deployment and rollback plans are
     documented. Complete. The application runtime, local Docker stack, CI
     marker suites, and normal dependency sets are Postgres-only. Keep the
     MySQL-to-Postgres backup import tooling and install its source driver only
     through the `mysql-migration` optional uv extra so existing backups remain
     migratable.
5. Modernize frontend tooling so client asset generation no longer depends on
   the legacy Node.js 6-era toolchain. Complete.
   - Replace Node 6 and `node-sass` with a modern npm/Dart Sass client asset
     build helper. Complete.
   - Migrate the remaining webpack 1 JavaScript bundling path to maintained
     tooling. Complete.
   - Decide whether generated client assets should stay gitignored build
     outputs or move to a reproducible release artifact workflow. Complete:
     keep local generated assets gitignored; build production assets in the
     production Docker or release artifact workflow.
6. Tighten `ruff` and `mypy` incrementally once dependency upgrades reduce
   legacy typing friction. Complete.
   - Scope existing mypy disabled error codes to the modules that still need
     them instead of applying them globally. Complete.
   - Add focused ruff rules that pass cleanly and catch real ambiguity.
     Complete.
   - Remove `logs_to_games.py` mypy exceptions after focused type cleanup.
     Complete.
   - Remove remaining `server.py` mypy exceptions after focused type cleanup.
     Complete.
7. Add production Docker and AWS deployment paths after the local Python
   runtime image is stable, including the production client asset build stage or
   release artifact workflow. Complete.
   - Add a production Dockerfile that builds generated client assets and runs
     the Python FastAPI gateway from a slim runtime image. Complete.
   - Document production image build, migration, runtime, and AWS deployment
     notes. Complete.
   - Add cloud-specific deployment configuration after the production container
     contract is reviewed. Complete for optional ECR image publishing.
   - Document GitHub repository variables, AWS OIDC trust policy, and minimal
     ECR push permissions for image publishing. Complete.

## Completed Baseline And Follow-Up

- Postgres is the sole application runtime database. The retained
  MySQL-to-Postgres importer is an optional operational tool for existing
  backups, not a runtime or rollback path.
- Docker supports the local development stack and the production image.
- AWS remains the preferred cloud target; optional ECR publishing is configured.
- README coverage and supported Python version badges are published from dynamic
  badge sources.
- Further dependency, packaging, and import work is tracked through GitHub
  issues and milestones.
