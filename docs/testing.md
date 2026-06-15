# Testing Strategy

Testing is the main safety mechanism for the planned refactor.

## Test Layers

- Unit tests cover pure Python helpers and game-rule behavior.
- Protocol tests cover the Python server input and output message format.
- Golden replay tests use historical game logs to protect current gameplay behavior.
- MySQL integration tests cover schema and persistence behavior.
- End-to-end smoke tests cover the full legacy stack while Node.js is still present.

## Pytest Markers

- `unit`: fast tests that do not require external services.
- `integration`: tests that exercise service boundaries.
- `golden`: replay or fixture-based regression tests.
- `mysql`: tests that require MySQL.
- `e2e`: end-to-end smoke tests.

## Coverage Policy

Coverage should be reported early, but strict thresholds should wait until meaningful coverage exists. The first target is useful regression protection, not an arbitrary percentage.

## Test Layout

- `tests/conftest.py` makes the legacy `server/` modules importable without changing runtime paths.
- `tests/test_id_managers.py` contains the migrated ID manager coverage.
- `tests/test_server_protocol.py` covers the Python server line protocol parser.
- `tests/test_server_messages.py` covers pending-message grouping and flushing behavior.
- `tests/fixtures/game_logs/` is reserved for historical log replay fixtures.

## Golden Replay Plan

Historical game logs should be added as fixtures after the tooling-only PR. The replay harness should make it easy to compare final states or expected protocol output without changing the current runtime behavior.

The first golden fixture is parser-level:

- Add a redacted log fixture under `tests/fixtures/game_logs/`.
- Add a matching `*.expected.json` file with normalized parser events.
- Add or extend tests that compare parser output to the expected snapshot.
- Add per-game extraction snapshots for `IndividualGameLogMaker` when a fixture should cover game-specific batches.

Future replay tests should build on this by processing complete historical game logs and comparing final game state, protocol output, or both.
