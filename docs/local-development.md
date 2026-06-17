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

The profile generates the gitignored `client/main/js/enums.js` file before starting `server/server.js`, then waits for the Python server to report a healthy `python.sock`.
The gateway removes any stale `javascript.sock` before starting so interrupted local runs do not block the next startup.

This profile exists to support the current split while Python backend parity is built out. Avoid expanding Node.js runtime behavior unless it is needed to preserve behavior during deprecation.

## Useful Commands

Stop containers:

```bash
docker compose down
```

Stop containers and remove the local MySQL data volume:

```bash
docker compose down --volumes
```

Run the test suite outside Docker with the modernization tooling:

```bash
uv run pytest
```
