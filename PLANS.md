# Modernization Plan

This document tracks the agreed modernization path for the Acquire codebase.

## Project Goal

Modernize the repository in phases so the team can safely perform a major refactor, retire the Node.js server, keep the Python backend, preserve current behavior through extensive pytest coverage, keep MySQL initially, and prepare for Docker-first local development with a later AWS deployment path.

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
- Add markers for `unit`, `integration`, `golden`, `mysql`, and `e2e`. Complete.
- Add coverage reporting with a 90% minimum threshold. Complete.
- Keep fast tests separate from MySQL and end-to-end tests. Complete.

Notes:

- The pytest suite now covers the core Python server modules, log parser/processor helpers, ORM helpers, cron helpers, and replay fixtures without requiring MySQL for fast checks.
- Coverage now has a 90% minimum threshold across the measured Python source without legacy-function exclusions.
- Docker-backed `mysql` and `e2e` marker fixtures are in place. MySQL coverage now exercises schema creation, seed data, runtime constraints, lookup persistence, transaction behavior, and completed-game log import persistence. Integration coverage now exercises Python server protocol flows for connection, chat, game creation, joining, starting, watching, leaving, disconnecting, and rejoining. E2E coverage now verifies UI/report endpoints, login, global/game chat, game creation, joining, starting, tile play, watching, leaving, and rejoining through the local browser gateway.

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
- Include MySQL as a local service. Complete.
- Support the Python gateway while the Node.js backend runtime is retired. Complete.
- Expose the local browser UI through the Python gateway. Complete.
- Generate legacy client assets inside the local Docker profile. Complete.
- Add `.env.example`. Complete.
- Document local setup, UI access, and teardown commands. Complete.

## Phase 5: Python Backend Consolidation

Status: complete.

Phase 5 will be completed as a sequence of focused PRs so each runtime boundary
change can be reviewed and validated independently.

1. Runtime boundary inventory. Complete. Document every Node-owned HTTP endpoint and
   SockJS message path, map each behavior to the existing Python equivalent or a
   missing Python implementation, and add any missing characterization tests
   before changing runtime code.
2. Move Node-owned HTTP endpoints to Python. Complete. Implement Python equivalents for
   non-websocket HTTP routes formerly served by `server/server.js` and prove
   existing browser flows still work through integration and e2e coverage.
3. Move auth and user checks fully into Python. Complete. Consolidate login,
   session, and user lookup behavior in the Python backend, with MySQL-backed
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

Status: in progress.

Phase 6 should be split into small PRs so dependency risk, database migration
risk, frontend build changes, and deployment changes can be reviewed
independently.

1. Upgrade Python runtime dependencies in controlled groups, starting with
   compatibility patches needed for supported Python versions. Complete.
2. Upgrade SQLAlchemy and add focused ORM/session regression coverage for any
   behavior that changes during the upgrade. Complete.
3. Add Alembic migrations for the current MySQL schema before changing database
   engines. Complete.
4. Plan and execute the MySQL-to-Postgres migration after migrations and
   persistence tests are in place. In progress.
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
     In progress. The latest staging rehearsal proved lookup, user,
     game-history, and key/value import/report validation for 61 sanitized
     report rows, but the source dump still had no rating rows and no `record`
     table. Because runtime stats reads do not rebuild historical `record` rows
     from imported games, full persisted rating/record stats rehearsal remains
     pending on a richer source dump before this gate can be marked complete.
     The partial rehearsal also verified stats reads and the gateway e2e suite
     against the imported Postgres target.
   - Remove MySQL-only runtime paths after deployment and rollback plans are
     documented. Pending.
     Legacy `initialize_database.py` reset command removal is complete;
     broader MySQL rollback-surface cleanup remains gated on production
     cutover ownership.
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

## Open Notes

- MySQL remains available for parity testing and rollback planning while
  Postgres becomes the local Docker default.
- Docker starts as local-development tooling only.
- AWS is the preferred future cloud target.
- README coverage badges should be added after the coverage reporting source is finalized.
- Runtime dependency upgrades are intentionally deferred.
