# Agent Instructions

This repository is in a modernization and refactor effort. Tooling, documentation, CI, and the pytest foundation are in place; the current goal is to deepen golden replay coverage before changing runtime behavior.

## Current Architecture

- `server/server.js` is the legacy Node.js HTTP and SockJS gateway.
- `server/server.py` contains the Python game server and socket protocol handling.
- MySQL is the current database.
- Client assets live under `client/` and are generated with the legacy shell scripts.
- `requirements.txt` remains the source of legacy runtime dependencies for now.
- `pyproject.toml` manages development tooling through `uv`.

## Important Constraints

- Do not change runtime behavior in tooling-only work.
- Do not upgrade legacy runtime dependencies until test coverage is strong.
- Do not remove the Node.js server until Python parity is covered by tests.
- Do not edit generated client assets directly.
- Keep linting and type checking permissive until golden tests protect behavior.
- Prefer small, reviewable changes with clear validation notes.
- Prefer module-sized test coverage PRs when a module can be covered cleanly without changing runtime behavior.
- In PR descriptions, list validation using canonical project commands such as `uv run pytest`; do not include local cache paths, virtualenv paths, or machine-specific environment overrides unless they are required for reviewers to reproduce the check.
- If the agent created a PR, the agent may update that PR's branch or description without asking for additional permission unless the change is destructive or changes the requested scope.

## Setup

Install `uv`, then run:

```bash
uv sync --group dev
```

The legacy runtime still uses:

```bash
pip install -r requirements.txt
yarn
```

## Validation

Run the current first-pass checks with:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

Run pre-commit hooks with:

```bash
uv run pre-commit run --all-files
```

## Modernization Priorities

1. Establish tooling, CI, and agent instructions.
2. Add pytest coverage around existing behavior.
3. Add golden replay tests from historical game logs.
4. Add local-development Docker support.
5. Consolidate the runtime into Python and deprecate Node.js.
6. Upgrade dependencies and plan the MySQL-to-Postgres migration after coverage is strong.
