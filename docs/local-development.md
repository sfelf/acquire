# Local Development

This project is in the Python-gateway consolidation phase:

- MySQL stores user and historical game data.
- `server/http_server.py` runs the default FastAPI HTTP and SockJS-compatible gateway.
- `server/server.py` remains available as the legacy socket-based Python game server for Node gateway parity checks.
- `server/server.js` is the legacy Node.js SockJS and HTTP gateway behind an opt-in compatibility profile.

The Docker Compose setup is intended for local development only while test coverage expands and the Node.js gateway is being retired.

The local Python image intentionally installs from `requirements.local-docker.txt` instead of the legacy `requirements.txt`. The legacy file still contains an old MySQL connector zip URL that is no longer reliably fetchable, and broad runtime dependency upgrades are deferred until coverage is stronger.

## Start The Local UI

Copy the example environment file if you want to customize local credentials:

```bash
cp .env.example .env
```

Generate the gitignored browser assets:

```bash
docker compose --profile client-build up --build client-assets
```

This one-time setup helper uses the legacy Node.js toolchain to compile
`client/main/css/main.css`, `client/stats/css/stats.css`,
`client/main/js/enums.js`, and `client/main/js/main.js` into the bind-mounted
checkout. It exits after the files are written and is not part of the default
running stack.

Start MySQL and the Python gateway:

```bash
docker compose up --build mysql python-gateway
```

The default gateway listens on port `9000`, serves the generated client files,
and handles SockJS traffic through the same origin at `/sockjs`.

Open the local UI:

```text
http://localhost:9000/
```

Set `ACQUIRE_UI_PORT` in `.env` to use a different host port:

```env
ACQUIRE_UI_PORT=9002
```

Initialize the local database in another terminal:

```bash
docker compose run --rm python-gateway python initialize_database.py
```

The Compose services pass the same `MYSQL_*` values from `.env` to MySQL, the Python ORM, the database initializer, the Python gateway, and the legacy Node gateway.

## Legacy Node Gateway

The Node.js gateway is available as an opt-in profile for local parity checks:

```bash
docker compose --profile legacy-node up --build mysql python-server node-gateway
```

Initialize the local database in another terminal if you have not already done so:

```bash
docker compose run --rm python-server python initialize_database.py
```

Then open the legacy local UI:

```text
http://localhost:9001/
```

The legacy profile includes the same client asset build helpers before starting `server/server.js`.
In Docker, the gateway listens on container port `9000`, publishes host port `9001` by default, serves the generated client files, and proxies SockJS traffic through the same origin at `/sockjs`.
Outside Docker, the gateway keeps the legacy default of listening on `javascript.sock`.
The gateway still removes any stale `javascript.sock` before starting so interrupted local runs do not block the next startup.

Set `ACQUIRE_LEGACY_UI_PORT` in `.env` to use a different host port for the legacy gateway:

```env
ACQUIRE_LEGACY_UI_PORT=9003
```

This profile exists as a known-good compatibility path while the Python gateway becomes the primary local runtime. Avoid expanding Node.js runtime behavior unless it is needed to preserve behavior during deprecation.

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

By default, the MySQL marker uses host port `33061` and the e2e marker exposes the local UI on host port `19000`. Override those with `ACQUIRE_MYSQL_TEST_PORT` or `ACQUIRE_E2E_PORT` if either port is already in use. Set `ACQUIRE_MYSQL_TEST_URL` or `ACQUIRE_E2E_URL` only when you want the tests to use an existing local stack instead of starting disposable Compose projects. `ACQUIRE_MYSQL_TEST_URL` must point at a disposable test schema because MySQL integration tests may create and drop ORM tables.
