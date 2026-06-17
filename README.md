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

## Local Docker development

Docker Compose support is available for local MySQL and the current Python game server:

```bash
cp .env.example .env
docker compose up --build mysql python-server
```

See [docs/local-development.md](docs/local-development.md) for database initialization, teardown, and the optional legacy Node.js gateway profile.

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
