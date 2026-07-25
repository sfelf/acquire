# Python Packaging

The Python source-layout migration is complete. `src/acquire/` is the sole
production Python source boundary, normal development uses an editable
uv-managed installation, and every application or test uses `acquire.*` imports.
No compatibility modules, legacy direct-file command paths, `sys.path`
injection, or `PYTHONPATH` configuration remain.

## Installation And Source Layout

The project uses `uv_build` with the conventional `src/acquire/` layout:

```bash
uv sync --group dev
uv run python -c "import acquire"
uv build --no-sources
```

Ruff, mypy, pytest coverage, pre-commit, Docker, Compose, and CI all measure or
install this canonical package boundary. Generated client assets remain
external build outputs under `client/`; they are not Python source or package
data.

## Supported Project Commands

Package metadata exposes exactly six supported project scripts:

| Command | Owner | Purpose |
| --- | --- | --- |
| `acquire-http-server` | `acquire.http_server` | Run the FastAPI and SockJS-compatible gateway |
| `acquire-setup-database` | `acquire.setup_database` | Apply packaged Alembic migrations and seed required lookup data |
| `acquire-generate-enums` | `acquire.enumsgen` | Generate or replace client enum definitions |
| `acquire-update-stats` | `acquire.stats` | Continuously import logs and publish stats |
| `acquire-migrate-mysql-to-postgres` | `acquire.migration.import_mysql_to_postgres` | Import a retained MySQL backup into Postgres |
| `acquire-validate-migration-reports` | `acquire.migration.validate_import_reports` | Validate the paired sanitized migration reports |

The former standalone socket game-server command and the ad hoc
`log_tools.main()` dispatcher are retired. Their importable packaged modules
remain available to the HTTP gateway, stats workflow, replay tools, and tests;
only the unsupported command surfaces were removed.

## Runtime And Operational Boundaries

Docker images install the project into a dedicated environment and invoke
supported commands without a repository-relative working directory. The HTTP
gateway receives explicit absolute main and stats asset roots in local and
production containers.

`acquire-update-stats` accepts explicit absolute `--stats-data-root` and
`--stats-temp-root` values, then the corresponding
`ACQUIRE_STATS_DATA_ROOT` and `ACQUIRE_STATS_TEMP_ROOT` environment variables.
Editable source layouts retain `client/stats/data` as the publication default
and `stats_temp` at the repository root as the staging default. Installed
artifacts require explicit roots.

The gateway treats host, port, and static roots as untrusted operator inputs.
It resolves hostnames across IPv4 and IPv6, binds and starts every usable
listener before Uvicorn begins, and uses fixed diagnostics for invalid input,
unavailable roots, resolution failures, bind failures, and concurrent listener
conflicts. Private paths and listener values are never reflected.

The migration commands preserve a separate legacy-source/current-target
schema boundary. Normal installations do not include
`mysql-connector-python`; the `mysql-migration` optional extra enables the
retained backup-import command:

```bash
uv run --extra mysql-migration acquire-migrate-mysql-to-postgres --help
uv run acquire-validate-migration-reports --help
```

## Remaining Artifact Closeout

Issue [#127](https://github.com/sfelf/acquire/issues/127) is the remaining
Packaging milestone gate. It owns final wheel and source-distribution
manifests, building a wheel from the unpacked source distribution, clean
installation outside the repository, packaged Alembic-resource verification,
and smoke tests for all six commands. It does not restore compatibility paths
or expand the supported command inventory.
