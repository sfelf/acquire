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
- Docker-backed `mysql` and `e2e` marker fixtures are in place. MySQL coverage now exercises schema creation, seed data, runtime constraints, lookup persistence, transaction behavior, and completed-game log import persistence. Integration coverage now exercises Python server protocol flows for connection, chat, game creation, joining, starting, watching, leaving, disconnecting, and rejoining.

## Phase 3: Golden Replay Tests

Status: expanded for the current fixture set; continue adding representative historical logs before refactoring.

- Use historical game logs as replay fixtures. Complete for the initial redacted real-server fixture.
- Add a replay harness for current game behavior. Complete for parser-level replay, individual-game extraction, and `LogProcessor` replay summaries.
- Store expected outputs or final states as golden files. Complete for the current fixture set.
- Document how to add new replay fixtures. Complete.
- Use replay tests as the main safety net for the major refactor. In progress.

Remaining work before the major refactor:

- Add MySQL-backed integration coverage for schema creation, seed data, and persistence behavior. Complete for the current refactor safety baseline; expand when refactor work changes persistence behavior.
- Add fuller integration and e2e coverage around the current Python/Node split. Integration coverage is complete for the current refactor safety baseline; continue expanding e2e parity coverage before retiring Node.js.
- Add more historical log fixtures when representative edge cases are available.
- Add richer final-state and replay-to-server synchronization golden assertions for future historical fixtures as they are added.

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

- Move Node-owned HTTP endpoints into Python.
- Move auth and user database checks into Python.
- Replace the Node.js SockJS gateway with a Python websocket path.
- Preserve the existing client protocol until tests prove it is safe to change.
- Remove the Node.js server from runtime once parity is covered.

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
