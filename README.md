# Acquire board game

[![CI](https://github.com/sfelf/acquire/actions/workflows/ci.yml/badge.svg?branch=feature/modernization-refactor)](https://github.com/sfelf/acquire/actions/workflows/ci.yml?query=branch%3Afeature%2Fmodernization-refactor)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
[![codecov](https://codecov.io/github/sfelf/acquire/branch/feature%2Fmodernization-refactor/graph/badge.svg)](https://app.codecov.io/github/sfelf/acquire/tree/feature%2Fmodernization-refactor)

This is the code for my Acquire board game program which can be played at [http://acquire.tlstyer.com/](http://acquire.tlstyer.com/).

## Modernization testing

The modernization branch uses `uv`, `pytest`, `ruff`, `mypy`, and GitHub Actions for Python 3.12, 3.13, and 3.14.

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

Current coverage is informational while golden replay tests are expanded before the major refactor. The coverage command generates `coverage.xml`, and CI uploads that report to Codecov so the README coverage badge can update without committing generated badge files to the repository. The repository must be connected to Codecov for uploads and the badge to resolve.

Run specific pytest marker layers with:

```bash
uv run pytest -m unit
uv run pytest -m golden
uv run pytest -m integration
uv run pytest -m mysql
uv run pytest -m e2e
```

MySQL and e2e marker runs create isolated Docker Compose projects when service URL environment variables are not set. Use `ACQUIRE_MYSQL_TEST_URL` or `ACQUIRE_E2E_URL` only when you want to point those tests at already-running services. Integration tests skip when the local environment blocks socket binding.

## Local Docker Development

Docker Compose support is available for local MySQL and the Python FastAPI gateway:

```bash
cp .env.example .env
docker compose --profile client-build run --rm client-assets
docker compose up --build mysql python-gateway
```

Initialize the local database in another terminal:

```bash
docker compose run --rm python-gateway python initialize_database.py
```

Then open [http://localhost:9000/](http://localhost:9000/).

The first command generates the gitignored browser assets once for the Python
gateway. Node.js is only used for that legacy client asset build step; the local
HTTP and SockJS runtime is Python-owned.

See [docs/local-development.md](docs/local-development.md) for UI access, database initialization, and teardown.

## Database migrations

Alembic tracks schema migrations for the Python database runtime:

```bash
uv run alembic upgrade head
uv run alembic current
```

The initial migration is a baseline for the current MySQL schema and required
lookup rows. Use `upgrade head` for an empty schema. For a database that was
already created by `initialize_database.py` and matches the current schema and
lookup rows, mark the baseline as already applied instead:

```bash
uv run alembic stamp head
```

Local reset workflows still use `initialize_database.py`; future schema or
required lookup-data changes should be added as Alembic revisions before the
MySQL-to-Postgres migration.

## Install dependencies

Install nodejs. I followed the [official instructions](https://nodejs.org/en/download/package-manager/#debian-and-ubuntu-based-linux-distributions):

```bash
curl -sL https://deb.nodesource.com/setup_6.x | sudo -E bash -
sudo apt-get install -y nodejs
```

Install yarn. I followed the [official instructions](https://yarnpkg.com/en/docs/cli/install):

```bash
curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | sudo apt-key add -
echo "deb https://dl.yarnpkg.com/debian/ stable main" | sudo tee /etc/apt/sources.list.d/yarn.list
sudo apt-get update && sudo apt-get install yarn
```

Install other dependencies.

```bash
sudo apt-get install mysql-server python3-pip python3-venv python3-wheel zopfli

python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt

yarn
```

## Download libraries for development use:

    cd lib
    curl http://cdnjs.cloudflare.com/ajax/libs/crypto-js/3.1.2/rollups/sha256.js > crypto-js.rollups.sha256-3.1.2.js
    curl http://cdnjs.cloudflare.com/ajax/libs/jquery/1.12.4/jquery.min.js > jquery-1.12.4.js
    curl http://cdnjs.cloudflare.com/ajax/libs/json3/3.3.2/json3.min.js > json3-3.3.2.js
    curl http://cdnjs.cloudflare.com/ajax/libs/history.js/1.8/native.history.min.js > native.history-1.8.js
    curl http://cdnjs.cloudflare.com/ajax/libs/sockjs-client/1.5.0/sockjs.min.js > sockjs-1.5.0.js
    curl http://cdnjs.cloudflare.com/ajax/libs/stacktrace.js/1.3.1/stacktrace-with-promises-and-json-polyfills.min.js > stacktrace-1.3.1.js
