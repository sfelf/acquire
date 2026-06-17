# Local Development

This project is still in the legacy split-runtime phase:

- MySQL stores user and historical game data.
- `server/server.py` runs the Python game server over `python.sock`.
- `server/server.js` is the legacy Node.js SockJS and HTTP gateway.

The Docker Compose setup is intended for local development only while test coverage expands and the Node.js gateway is being retired.

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

The initializer currently uses the legacy root password and Unix socket assumptions from the existing codebase.

## Legacy Node Gateway

The Node.js gateway is available as an opt-in profile for local parity checks:

```bash
docker compose --profile legacy-node up --build mysql python-server node-gateway
```

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
