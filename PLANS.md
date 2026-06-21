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
- Docker-backed `mysql` and `e2e` marker fixtures are in place. MySQL coverage now exercises schema creation, seed data, runtime constraints, lookup persistence, transaction behavior, and completed-game log import persistence. Integration coverage now exercises Python server protocol flows for connection, chat, game creation, joining, starting, watching, leaving, disconnecting, and rejoining. E2E coverage now verifies UI/report endpoints, login, global/game chat, game creation, joining, starting, tile play, watching, leaving, and rejoining through the legacy Node gateway into Python.

## Phase 3: Golden Replay Tests

Status: complete.

- Use historical game logs as replay fixtures. Complete for the current refactor safety baseline.
- Add a replay harness for current game behavior. Complete for parser-level replay, individual-game extraction, and `LogProcessor` replay summaries.
- Store expected outputs or final states as golden files. Complete for the current refactor safety baseline.
- Document how to add new replay fixtures. Complete.
- Use replay tests as the main safety net for the major refactor. Complete for the current refactor safety baseline.

Notes:

- Add MySQL-backed integration coverage for schema creation, seed data, and persistence behavior. Complete for the current refactor safety baseline; expand when refactor work changes persistence behavior.
- Add fuller integration and e2e coverage around the current Python/Node split. Complete for the current refactor safety baseline; add targeted parity cases if Node retirement uncovers additional gateway behavior.
- Historical fixtures include synthetic parser coverage and a representative redacted real-server fixture with summary, replay, final-state, and replay-to-server sync golden assertions.
- Future historical fixtures can still be added when new edge cases are discovered during refactor work, but they are no longer blocking Phase 3 completion.

## Phase 4: Local Development Docker

Status: complete.

- Add Docker Compose for local development. Complete.
- Include MySQL as a local service. Complete.
- Support the current Node.js and Python split without over-investing in Node.js as a long-term runtime. Complete.
- Expose the legacy Node gateway for browser UI parity checks. Complete.
- Generate legacy client assets inside the local Docker profile. Complete.
- Add `.env.example`. Complete.
- Document local setup, UI access, and teardown commands. Complete.

## Phase 5: Python Backend Consolidation

Status: planned.

Phase 5 will be completed as a sequence of focused PRs so each runtime boundary
change can be reviewed and validated independently.

1. Runtime boundary inventory. Document every Node-owned HTTP endpoint and
   SockJS message path, map each behavior to the existing Python equivalent or a
   missing Python implementation, and add any missing characterization tests
   before changing runtime code.
2. Move Node-owned HTTP endpoints to Python. Implement Python equivalents for
   non-websocket HTTP routes currently served by `server/server.js`, keep the
   Node gateway running during the transition, and prove existing browser flows
   still work through integration and e2e coverage.
3. Move auth and user checks fully into Python. Consolidate login, session, and
   user lookup behavior in the Python backend, with MySQL-backed coverage for
   successful credentials, failed credentials, missing users, existing users,
   and session edge cases.
4. Add a Python websocket or SockJS-compatible gateway path. Preserve the
   existing client protocol, keep the Node gateway available as the known-good
   comparison path, and add parity tests for representative workflows.
5. Switch local development and e2e tests to the Python gateway by default.
   Update Docker Compose, local development docs, and e2e defaults while keeping
   the legacy Node gateway behind an explicit compatibility profile.
6. Remove Node.js from the main runtime path. Remove the Node gateway from the
   default local runtime, remove runtime dependency on Node-generated artifacts
   where only the gateway needed them, and update agent/project docs to reflect
   Python as the primary backend.
7. Cleanup follow-up. Delete dead Node server code only after the Python path is
   proven stable, remove obsolete tests, docs, scripts, and dependency
   references, and tighten CI around the Python-only runtime path.

## Phase 6: Dependency And Deployment Modernization

- Upgrade Python runtime dependencies.
- Upgrade SQLAlchemy.
- Add Alembic migrations.
- Plan and execute a MySQL-to-Postgres migration.
- Modernize frontend tooling.
- Tighten `ruff` and `mypy`.
- Add production Docker and AWS deployment paths.

## Open Notes

- MySQL remains the database until test coverage is strong.
- Docker starts as local-development tooling only.
- AWS is the preferred future cloud target.
- README coverage badges should be added after the coverage reporting source is finalized.
- Runtime dependency upgrades are intentionally deferred.
