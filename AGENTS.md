# Agent Instructions

The six-phase modernization plan is complete. Tooling, documentation, CI,
Docker-backed development, pytest coverage, Python backend consolidation,
Postgres migration support, and production image publishing are in place. New
work should follow GitHub issues and milestones for the major refactor.

## Current Architecture

- `src/acquire/http_server.py` contains the FastAPI app for the default local
  HTTP gateway.
- `src/acquire/realtime.py` contains the SockJS-compatible WebSocket adapter.
- `src/acquire/game_server.py` contains the Python game engine and legacy
  socket protocol handling.
- `src/acquire/log_tools.py`, `src/acquire/recreate_game.py`, and
  `src/acquire/stats.py` contain the replay, snapshot-restoration, and stats
  maintenance tooling.
- `src/acquire/` is the sole production Python source boundary; use installed
  project commands or `acquire.*` imports.
- `docs/packaging.md` defines the completed source-layout, distribution, and
  installed-command contract.
- Postgres is the only application runtime database. MySQL support is limited
  to `acquire.migration`, installed with the `mysql-migration` optional uv extra
  for importing existing backups.
- Client assets and their npm manifests live under `client/`; use the canonical
  npm scripts there or the opt-in `client-build` Compose profile.
- `pyproject.toml` is the sole source of direct application dependencies,
  optional operational extras, and development dependency groups.
- `uv.lock` is the sole reproducible resolved Python dependency set.

## Important Constraints

- Do not change runtime behavior in tooling-only work.
- Keep dependency upgrades issue-scoped and covered by focused regression
  tests; do not combine broad upgrades with unrelated refactors.
- Do not add Node.js services back to the backend runtime path; keep Node usage
  limited to explicit client asset build tooling.
- Do not edit generated client assets directly.
- Preserve the current `ruff` and `mypy` baseline; new code must pass both
  checks without adding broad exceptions.
- Prefer small, reviewable changes with clear validation notes.
- Prefer module-sized test coverage PRs when a module can be covered cleanly without changing runtime behavior.
- Use FastAPI and Pydantic for new Python HTTP routes when they fit the endpoint contract, while preserving existing response bodies and error codes unless an issue explicitly changes the public contract.
- Add Google-style docstrings for new non-test Python modules, classes, functions, and methods. Always include a useful summary line. Include `Args:` and `Returns:` sections when there are arguments or return values to document; omit those sections when they would only say `None`.
- Prefer concise docstrings, but add a longer paragraph after the summary when the callable has non-obvious business or domain rules, mutates state, persists data, sends messages, publishes events, mutates arguments, relies on important preconditions, has ordering or lifecycle constraints, handles surprising edge cases, coordinates multiple systems, returns values that need interpretation, raises meaningful exceptions, uses exceptions as part of its contract, has security/authorization/concurrency/idempotency/retry/transaction concerns, is a public API or service boundary, represents an important abstraction/lifecycle/protocol/domain concept, or exists for a reason that is not clear from the local method name. Do not add longer descriptions that merely repeat the function name, restate type information, or explain implementation details callers do not need.
- When reviewing docstrings, classify each reviewed docstring as `Summary only is sufficient`, `Longer description recommended`, or `Longer description required`, with a brief reason or the specific missing caller-relevant context.
- In PR descriptions, list validation using canonical project commands such as `uv run pytest`; do not include local cache paths, virtualenv paths, or machine-specific environment overrides unless they are required for reviewers to reproduce the check.
- Before opening or updating a PR, review coverage for newly changed code and add targeted tests for new branches, error paths, and cleanup paths so Codecov patch coverage does not fail even when total project coverage remains high.
- If the agent created a PR, the agent may update that PR's branch or description without asking for additional permission unless the change is destructive or changes the requested scope.

## Pre-PR And Push Workflow

Before completing a task, opening a PR, or pushing updates to an existing PR, perform an autonomous local code review of the diff and directly fix any issues found. Do not stop to produce a separate textual review report or ask for permission to make non-destructive fixes within the requested scope.

During the review, check for:

- Logic regressions against the target branch architecture and current modernization constraints.
- Missing edge-case handling, including error paths, `None` handling, boundary values, cleanup paths, and performance-sensitive changes.
- Stale documentation, including inline comments, docstrings, `README.md`, docs under `docs/`, and API or protocol notes affected by changed signatures or behavior.
- PR-description accuracy. Update any local PR description markdown file when one exists; otherwise update the GitHub PR description for agent-created PRs so it precisely matches the finalized behavior and validation.

After fixing review findings, run the repo-appropriate verification commands:

```bash
uv run ruff check .
uv run mypy
uv run pytest
uv run pre-commit run --all-files
```

If any verification step fails, treat the failure as a new issue, fix it, and rerun the failing command until it passes. Add or adjust tests when fixes touch changed code paths or uncovered branches.

Once the review and verification are complete, include only brief execution-log entries in the chat using this format when applicable:

```text
**[Fixed Code]:** <File Name> - <Brief fix description>
**[Updated Docs]:** <File Name> - <Brief documentation adjustment>
**[Updated PR Description]:** <Brief summary of PR text changes>
```

## Setup

Install `uv`, then run:

```bash
uv sync --group dev
```

The client asset build helpers use:

```bash
cd client
npm ci
npm run build:client
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

## Current Priorities

1. Follow GitHub issues and milestones for the next major-refactor work.
2. Keep characterization, integration, database, golden, and e2e tests green
   while preparing the major refactor.
3. Preserve the optional MySQL-backup import path until existing backups no
   longer need to be migrated.

`PLANS.md` preserves the completed modernization record and documents approved
delivery order and decisions for active milestones. GitHub issues and milestones
remain authoritative for current scope, status, dependencies, and acceptance
criteria; update `PLANS.md` when an approved issue change alters the recorded
sequence or decisions.
