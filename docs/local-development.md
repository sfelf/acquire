# Local Development

This project is still in the legacy split-runtime phase:

- MySQL stores user and historical game data.
- `server/server.py` runs the Python game server over `python.sock`.
- `server/server.js` is the legacy Node.js SockJS and HTTP gateway.

The Docker Compose setup is intended for local development only while test coverage expands and the Node.js gateway is being retired.

The local Python image intentionally installs from `requirements.local-docker.txt` instead of the legacy `requirements.txt`. The legacy file still contains an old MySQL connector zip URL that is no longer reliably fetchable, and broad runtime dependency upgrades are deferred until coverage is stronger.

## Start MySQL And Python

Copy the example environment file if you want to customize local credentials:

```bash
cp .env.example .env
```

Start MySQL and the Python game server:

```bash
docker compose up --build mysql python-server
```

This starts the Python backend only. It does not expose the browser UI because the current UI still depends on the legacy Node.js gateway.

Initialize the local database in another terminal:

```bash
docker compose run --rm python-server python initialize_database.py
```

The Compose services pass the same `MYSQL_*` values from `.env` to MySQL, the Python ORM, the database initializer, and the legacy Node gateway.

## Legacy Node Gateway

The Node.js gateway is available as an opt-in profile for local parity checks:

```bash
docker compose --profile legacy-node up --build mysql python-server node-gateway
```

Initialize the local database in another terminal if you have not already done so:

```bash
docker compose run --rm python-server python initialize_database.py
```

Then open the local UI:

```text
http://localhost:9000/
```

Set `ACQUIRE_UI_PORT` in `.env` to use a different host port:

```env
ACQUIRE_UI_PORT=9001
```

The profile generates the gitignored client assets before starting `server/server.js`: `client/main/css/main.css`, `client/stats/css/stats.css`, `client/main/js/enums.js`, and `client/main/js/main.js`.
In Docker, the gateway listens on port `9000`, serves the generated client files, and proxies SockJS traffic through the same origin at `/sockjs`.
Outside Docker, the gateway keeps the legacy default of listening on `javascript.sock`.
The gateway still removes any stale `javascript.sock` before starting so interrupted local runs do not block the next startup.

This profile exists to support the current split while Python backend parity is built out. Avoid expanding Node.js runtime behavior unless it is needed to preserve behavior during deprecation.

## Useful Commands

Stop containers:

```bash
docker compose down
```

Stop containers and remove the local MySQL data volume, MySQL socket volume, and container-side Node dependency cache:

```bash
docker compose down --volumes
```

Run the test suite outside Docker with the modernization tooling:

```bash
uv run pytest
```

Run Docker-backed marker tests with the same marker commands used in CI and review:

```bash
uv run pytest -m mysql
uv run pytest -m e2e
```

By default, the MySQL marker uses host port `33061` and the e2e marker exposes the local UI on host port `19000`. Override those with `ACQUIRE_MYSQL_TEST_PORT` or `ACQUIRE_E2E_PORT` if either port is already in use. Set `ACQUIRE_MYSQL_TEST_URL` or `ACQUIRE_E2E_URL` only when you want the tests to use an existing local stack instead of starting disposable Compose projects.
