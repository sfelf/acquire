# Agent Instructions

This repository is in a modernization and refactor effort. Tooling, documentation, CI, Docker-backed local development, and the pytest foundation are in place; the current goal is to deepen marker coverage, including MySQL, integration, e2e, and golden replay tests, before changing runtime behavior.

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
- Add Google-style docstrings for new non-test Python modules, classes, functions, and methods. Always include a useful summary line. Include `Args:` and `Returns:` sections when there are arguments or return values to document; omit those sections when they would only say `None`.
- Prefer concise docstrings, but add a longer paragraph after the summary when the callable has non-obvious business or domain rules, mutates state, persists data, sends messages, publishes events, mutates arguments, relies on important preconditions, has ordering or lifecycle constraints, handles surprising edge cases, coordinates multiple systems, returns values that need interpretation, raises meaningful exceptions, uses exceptions as part of its contract, has security/authorization/concurrency/idempotency/retry/transaction concerns, is a public API or service boundary, represents an important abstraction/lifecycle/protocol/domain concept, or exists for a reason that is not clear from the local method name. Do not add longer descriptions that merely repeat the function name, restate type information, or explain implementation details callers do not need.
- When reviewing docstrings, classify each reviewed docstring as `Summary only is sufficient`, `Longer description recommended`, or `Longer description required`, with a brief reason or the specific missing caller-relevant context.
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
