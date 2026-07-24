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
uv run pytest --cov=server --cov-report=term-missing:skip-covered --cov-report=xml
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

## Local Docker Development

Docker Compose support is available for local Postgres and the Python FastAPI gateway:

```bash
cp .env.example .env
docker compose --profile client-build run --rm client-assets
docker compose up --build postgres python-gateway
```

Initialize the local database in another terminal:

```bash
docker compose run --rm python-gateway python setup_database.py
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

Alembic tracks schema migrations for the Python database runtime:

```bash
uv run alembic upgrade head
uv run alembic current
```

The initial migration is a baseline for the current schema and required lookup
rows. Use `upgrade head` for an empty schema. For a database that was already
created by the pre-Alembic reset workflow and matches the current schema and
lookup rows, mark the baseline as already applied instead:

```bash
uv run alembic stamp head
```

Local Docker setup uses Alembic through `acquire.setup_database`; the current
direct-file command is a temporary compatibility entry point until issue #110
adds the installed project script. Future schema or required lookup-data
changes should be added as Alembic revisions.

## Install dependencies

Install `uv`, then create the project environment:

```bash
uv sync --group dev
```

Install Node.js 22 LTS or newer when you want to build client assets outside
Docker, then run:

```bash
npm ci
npm run build:client
```

Install the `zopfli` system package when running the legacy stats compression
workflow.

### Legacy Python Installation

`requirements.txt` remains available temporarily for compatibility with the
pre-uv installation path. New development should use `uv`.

```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
pip3 install --no-deps -e .
```

The editable project install exposes the `acquire` package while
`requirements.txt` remains the source of dependencies for this transitional
workflow.

## Download libraries for development use:

    cd lib
    curl http://cdnjs.cloudflare.com/ajax/libs/crypto-js/3.1.2/rollups/sha256.js > crypto-js.rollups.sha256-3.1.2.js
    curl http://cdnjs.cloudflare.com/ajax/libs/jquery/1.12.4/jquery.min.js > jquery-1.12.4.js
    curl http://cdnjs.cloudflare.com/ajax/libs/json3/3.3.2/json3.min.js > json3-3.3.2.js
    curl http://cdnjs.cloudflare.com/ajax/libs/history.js/1.8/native.history.min.js > native.history-1.8.js
    curl http://cdnjs.cloudflare.com/ajax/libs/sockjs-client/1.5.0/sockjs.min.js > sockjs-1.5.0.js
    curl http://cdnjs.cloudflare.com/ajax/libs/stacktrace.js/1.3.1/stacktrace-with-promises-and-json-polyfills.min.js > stacktrace-1.3.1.js
