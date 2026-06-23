# Local Development

The local development stack now uses the Python gateway as the default runtime:

- Postgres stores local user and historical game data for the default Docker stack.
- `server/http_server.py` runs the default FastAPI HTTP and SockJS-compatible gateway.
- `server/server.py` owns the Python game state and gameplay command handling.
- Node.js is used only by the opt-in client asset build helper.

The Docker Compose setup is intended for local development only while deployment support matures.

The local Python image intentionally installs from `requirements.local-docker.txt` so
Docker can keep a narrow, already-tested dependency surface while the legacy
runtime requirements are modernized in controlled groups. SQLAlchemy remains
intentionally pinned until the dedicated ORM upgrade step.

## Start The Local UI

Copy the example environment file if you want to customize local credentials:

```bash
cp .env.example .env
```

Generate the gitignored browser assets:

```bash
docker compose --profile client-build run --rm client-assets
```

This one-time setup helper uses the npm client build scripts to compile
`client/main/css/main.css`, `client/stats/css/stats.css`,
`client/main/js/enums.js`, and `client/main/js/main.js` into the bind-mounted
checkout. It exits after the files are written and is not part of the default
running stack.

See `docs/client-assets.md` for the source/build-output boundary and deployment
packaging follow-up.

Start Postgres and the Python gateway:

```bash
docker compose up --build postgres python-gateway
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
docker compose run --rm python-gateway python setup_database.py
```

This applies Alembic migrations and required lookup data to the configured
database without dropping existing data. The Compose services pass the same
`POSTGRES_*` values from `.env` to Postgres, Alembic, the Python ORM, and the
Python gateway.

## Useful Commands

Stop containers:

```bash
docker compose down
```

Stop containers and remove the local Postgres data volume and container-side Node dependency cache used by the client build helper:

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
uv run pytest -m postgres
uv run pytest -m e2e
```

By default, the MySQL marker uses host port `33061`, the Postgres marker chooses an available host port, and the e2e marker exposes the local UI on host port `19000`. Override those with `ACQUIRE_MYSQL_TEST_PORT`, `ACQUIRE_POSTGRES_TEST_PORT`, or `ACQUIRE_E2E_PORT` when you need a fixed port. Set `ACQUIRE_MYSQL_TEST_URL`, `ACQUIRE_POSTGRES_TEST_URL`, or `ACQUIRE_E2E_URL` only when you want the tests to use an existing local stack instead of starting disposable Compose projects. Database marker URLs must point at disposable test schemas because marker tests may create and drop tables.
