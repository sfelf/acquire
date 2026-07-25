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
uv run python scripts/verify_distribution.py
```

Ruff, mypy, pytest coverage, pre-commit, Docker, Compose, and CI all measure or
install this canonical package boundary. Generated client assets remain
external build outputs under `client/`; they are not Python source or package
data.

## Distribution Artifact Contract

The wheel contains only the tracked `src/acquire/` runtime package, its
Alembic configuration and migrations, project metadata, and the six entry
points below. It contains no tests, fixtures, client assets, repository
tooling, credentials, database dumps, sockets, caches, bytecode, coverage
output, or temporary reports.

The source distribution contains `pyproject.toml`, `README.md`, the tracked
`src/acquire/` package, the tracked `tests/` source, and the sanitized
`tests/fixtures/game_logs/` fixtures. Those tests are an inventory contract:
the source distribution intentionally omits repository CI, Docker, client,
documentation, lockfile, and development-tooling resources, so it does not
promise that the complete repository integration suite can run from the
archive alone.

From a repository checkout, `scripts/verify_distribution.py` asserts both
complete manifests, builds a wheel from the unpacked source distribution,
independently installs the direct and rebuilt wheels in clean temporary
environments outside the repository, and exercises both installed resource and
command boundaries. CI runs this verification on every supported Python
version. All release conditions use explicit failures rather than Python
assertions, so optimization cannot disable checks or skip their side effects.

| Verification state | Result |
| --- | --- |
| Both manifests exactly match and both wheels install | Continue to command and resource smoke tests |
| An artifact is empty, missing a required file, or contains an unexpected file | Fail before installation |
| Build, rebuild, installation, or command execution is partial or fails | Fail without treating partial output as releasable |
| A dependency index or external service is temporarily unavailable | Rerun the complete verifier after the environment recovers |
| Artifact or command outcome is unknown | Fail closed; never infer readiness from incomplete evidence |

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

## Clean-Install Verification

The verifier confirms every command resolves from both the editable
development install and the rebuilt clean wheel. For the installed gateway it
serves representative files from temporary absolute main and stats roots, and
checks that missing or relative roots fail with fixed diagnostics. It also
confirms explicit stats publication and staging roots have no source-layout
dependency.

The Postgres marker layer runs the same clean-wheel verifier against a fresh
database and calls `acquire-setup-database` twice. This proves the installed
command locates its packaged Alembic resources, upgrades without a repository
checkout, and remains idempotent. The verifier first confirms a normal wheel
install has no MySQL connector, then installs the `mysql-migration` extra and
imports the retained backup importer with `mysql.connector` available.
