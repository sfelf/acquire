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

## Golden Replay Plan

Historical game logs should be added as fixtures after the tooling-only PR. The replay harness should make it easy to compare final states or expected protocol output without changing the current runtime behavior.
