# Acquire board game

[![CI](https://github.com/sfelf/acquire/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sfelf/acquire/actions/workflows/ci.yml?query=branch%3Amain)
![Supported Python versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
[![Project coverage](https://codecov.io/github/sfelf/acquire/branch/main/graph/badge.svg)](https://app.codecov.io/github/sfelf/acquire/tree/main)

## About This Fork

This repository is an independently maintained fork of
[tlstyer/acquire](https://github.com/tlstyer/acquire). The original project,
which can be played at [acquire.tlstyer.com](http://acquire.tlstyer.com/),
provided the foundation for this work. We are grateful to tlstyer and the
project's contributors for creating and sharing it.

This fork is not affiliated with, endorsed by, or maintained in collaboration
with tlstyer. Its changes are developed independently and are not currently
intended for contribution back to the original repository.

This fork preserves the original project's foundation while modernizing the
codebase, development tooling, testing, deployment process, and architecture.
Its goal is to support continued maintenance and the addition of new game
features. This repository is not the source currently deployed at
`acquire.tlstyer.com`.

The completed modernization, Packaging, and dependency-hygiene decisions are
preserved in
[docs/history/modernization-and-packaging.md](docs/history/modernization-and-packaging.md).
GitHub issues and milestones remain authoritative for active work.

## Development And Testing

The project uses `uv`, `pytest`, `ruff`, `mypy`, and GitHub Actions for Python
3.12, 3.13, and 3.14.

Run the fast validation suite with:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

Run the informational coverage report with:

```bash
uv run pytest --cov=src/acquire --cov-report=term-missing:skip-covered --cov-report=xml
```

The test configuration enforces at least 90% total coverage. The coverage
command generates `coverage.xml`, and CI uploads that report to Codecov so the
README coverage badge can update without committing generated badge files to
the repository. The repository must be connected to Codecov for uploads and
the badge to resolve.

Run specific pytest marker layers with:

```bash
uv run pytest -m unit
uv run pytest -m golden
uv run pytest -m integration
uv run pytest -m postgres
uv run pytest -m e2e
```

Postgres and e2e marker runs create isolated Docker Compose projects when
service URL environment variables are not set. Use
`ACQUIRE_POSTGRES_TEST_URL` or `ACQUIRE_E2E_URL` only when you want to point
those tests at already-running services. Integration tests skip when the local
environment blocks socket binding.

From a repository checkout, verify the exact wheel and source-distribution
manifests, rebuild a wheel from the source distribution, and exercise all six
commands from clean installs outside the repository with:

```bash
uv run python scripts/verify_distribution.py
```

The Python wheel intentionally excludes generated browser assets. Deployments
must build those assets separately and pass explicit main and stats roots to
`acquire-http-server`.

## Local Docker Development

Docker Compose support is available for local Postgres and the Python FastAPI gateway:

```bash
cp .env.example .env
docker compose --profile client-build run --rm client-assets
docker compose up --build postgres python-gateway
```

Initialize the local database in another terminal:

```bash
docker compose run --rm python-gateway acquire-setup-database
```

Then open [http://localhost:9000/](http://localhost:9000/).

The first command generates the gitignored browser assets once for the Python
gateway with the modern npm client build helper; the local HTTP and SockJS
runtime is Python-owned.

See [docs/local-development.md](docs/local-development.md) for UI access, database initialization, and teardown.

## Deployment

Build the production Docker image with:

```bash
docker build -t acquire:production .
```

The production image builds generated client assets in a Node stage and runs
the Python FastAPI gateway from a slim Python runtime. See
[docs/deployment.md](docs/deployment.md) for migration, runtime, and AWS
deployment notes.

## Database migrations

Alembic tracks schema migrations for the Python database runtime. Apply the
packaged migration boundary with the installed command:

```bash
uv run acquire-setup-database
```

The command loads configuration and revisions from the installed `acquire`
package, upgrades empty and versioned schemas, and safely recognizes the exact
pre-Alembic baseline. Direct Alembic CLI invocation from the repository root is
unsupported; no root configuration is provided. Future schema or required
lookup-data changes should be added as packaged Alembic revisions.

## Stats updater

Run the continuous log import and stats publication worker with explicit
absolute roots:

```bash
uv run acquire-update-stats \
  --stats-data-root /srv/acquire/stats/data \
  --stats-temp-root /srv/acquire/stats/staging
```

`ACQUIRE_STATS_DATA_ROOT` and `ACQUIRE_STATS_TEMP_ROOT` provide equivalent
environment fallbacks. Editable source layouts retain their validated local
defaults. The updater retries operational failures at 60-second intervals and
uses fixed diagnostics that do not include database values, paths, log
contents, or exception details.

## Install dependencies

Install `uv`, then create the project environment:

```bash
uv sync --group dev
```

`pyproject.toml` declares all direct Python dependencies and `uv.lock` pins the
reproducible resolved environment. Use uv to change or install Python
dependencies so both files remain synchronized.

Install Node.js 22 and npm 10 or newer when you want to build client assets
outside Docker, then run:

```bash
cd client
npm ci
npm run build:client
npm run verify:client
```

Install the `zopfli` system package when running the legacy stats compression
workflow.

## Download libraries for development use:

    cd lib
    curl http://cdnjs.cloudflare.com/ajax/libs/crypto-js/3.1.2/rollups/sha256.js > crypto-js.rollups.sha256-3.1.2.js
    curl http://cdnjs.cloudflare.com/ajax/libs/jquery/1.12.4/jquery.min.js > jquery-1.12.4.js
    curl http://cdnjs.cloudflare.com/ajax/libs/json3/3.3.2/json3.min.js > json3-3.3.2.js
    curl http://cdnjs.cloudflare.com/ajax/libs/history.js/1.8/native.history.min.js > native.history-1.8.js
    curl http://cdnjs.cloudflare.com/ajax/libs/sockjs-client/1.5.0/sockjs.min.js > sockjs-1.5.0.js
    curl http://cdnjs.cloudflare.com/ajax/libs/stacktrace.js/1.3.1/stacktrace-with-promises-and-json-polyfills.min.js > stacktrace-1.3.1.js
