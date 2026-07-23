# ADR 0001: Test-First Modernization Strategy

## Status

Accepted.

## Context

The codebase is preparing for a major refactor. The long-term goal is to retire the Node.js server and keep the backend in Python. The current application has limited automated test coverage and legacy runtime dependencies.

## Decision

Modernization will proceed in phases:

1. Add permissive tooling, CI, and agent workflow docs.
2. Add pytest coverage around existing behavior.
3. Add historical-log golden replay tests.
4. Add local-development Docker support.
5. Consolidate backend behavior into Python.
6. Upgrade dependencies and add production deployment paths.

## Consequences

- The first PR intentionally avoids runtime behavior changes.
- Linting and type checking start lenient and tighten later.
- Runtime dependency upgrades are deferred until tests can catch regressions.
- Node.js remains in place until Python parity is tested.

## Outcome

All six phases were completed by July 23, 2026. The repository now has strict
linting and typing checks, broad pytest and golden replay coverage,
Docker-backed local development, a Python-owned backend runtime, Postgres as
the application database, modern client build tooling, and a production image
with optional AWS ECR publishing.

The original sequencing constraints above remain part of the decision record;
they no longer describe active project limitations. Follow-up packaging,
dependency, and refactor work is tracked through GitHub issues and milestones.
