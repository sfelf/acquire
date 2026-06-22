# Testing Strategy

Testing is the main safety mechanism for the planned refactor.

## Test Layers

- Unit tests cover pure Python helpers and game-rule behavior.
- Protocol tests cover the Python server input and output message format.
- Golden replay tests use historical game logs to protect current gameplay behavior.
- MySQL integration tests cover schema and persistence behavior.
- Postgres smoke tests cover the Docker-backed Postgres fixture that will be
  expanded during the database migration.
- End-to-end smoke tests cover the default Python gateway stack.

## Pytest Markers

- `unit`: fast tests that do not require external services.
- `integration`: tests that exercise service boundaries.
- `golden`: replay or fixture-based regression tests.
- `mysql`: tests that require MySQL.
- `postgres`: tests that require Postgres.
- `e2e`: end-to-end smoke tests.

## Coverage Policy

Coverage is reported in CI and must stay at or above 90%. The threshold should continue to rise only when the added tests protect behavior that matters for the Python refactor.

All Python source included in the coverage target should count toward the coverage metric. Do not add coverage exclusions for legacy paths solely because they are difficult to exercise; add focused tests or move code out of the measured source set only when the project intentionally stops treating it as maintained Python source.

Run coverage locally with:

```bash
uv run pytest --cov=server --cov-report=term-missing:skip-covered
```

## Test Layout

- `tests/conftest.py` makes the legacy `server/` modules importable without changing runtime paths.
- `tests/conftest.py` also provides Docker-backed fixtures for marker tests that need MySQL or the local browser UI.
- `tests/test_id_managers.py` contains the migrated ID manager coverage.
- `tests/test_server_protocol.py` covers the Python server line protocol parser.
- `tests/test_server_messages.py` covers pending-message grouping and flushing behavior.
- `tests/fixtures/game_logs/` is reserved for historical log replay fixtures.

Run individual marker layers with:

```bash
uv run pytest -m unit
uv run pytest -m golden
uv run pytest -m integration
uv run pytest -m mysql
uv run pytest -m postgres
uv run pytest -m e2e
```

The `mysql` marker starts a disposable Docker Compose MySQL service when `ACQUIRE_MYSQL_TEST_URL` is not set. Set `ACQUIRE_MYSQL_TEST_URL` only when you want the tests to use an existing disposable test schema; MySQL integration tests may create and drop ORM tables. The `postgres` marker starts a disposable Docker Compose Postgres service when `ACQUIRE_POSTGRES_TEST_URL` is not set. Set `ACQUIRE_POSTGRES_TEST_URL` only when you want the tests to use an existing disposable test schema. The `e2e` marker generates client assets with the opt-in client build helper, then starts the local Compose stack with the Python gateway when `ACQUIRE_E2E_URL` is not set. Set `ACQUIRE_E2E_URL` only when you want the tests to use an existing local stack.

GitHub Actions runs the fast Python matrix on Python 3.12, 3.13, and 3.14.
The Docker-backed `mysql` and `e2e` marker suites run in a separate Python 3.13
job so pull requests exercise persistence and the local Python gateway without
tripling Docker build time across the full version matrix.

## Golden Replay Plan

Historical game logs should be added as fixtures after the tooling-only PR. The replay harness should make it easy to compare final states or expected protocol output without changing the current runtime behavior.

The first golden fixture is parser-level:

- Add a redacted log fixture under `tests/fixtures/game_logs/`.
- Add a matching `*.expected.json` file with normalized parser events.
- Add or extend tests that compare parser output to the expected snapshot.
- Add per-game extraction snapshots for `IndividualGameLogMaker` when a fixture should cover game-specific batches.

Fuller replay tests process complete historical game logs with `LogProcessor` and compare final game summaries. Future replay tests should build on this by comparing richer final game state, protocol output, or both.

Real-server fixtures should be redacted before commit. Preserve game commands and structured log entries, but replace usernames, IP addresses, and socket identifiers with stable fake values.
