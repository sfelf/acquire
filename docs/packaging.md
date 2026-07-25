# Python Packaging

The Packaging milestone moves the Python application from working-directory
imports under `server/` to an installed package under `src/acquire/`. GitHub
issues and the Packaging milestone remain authoritative for current scope,
dependencies, status, and acceptance criteria.

## Package Foundation

The project uses `uv_build` with the conventional `src/acquire/` layout. A
normal `uv sync --group dev` installs the project in editable mode, so package
imports resolve to the working tree during development. `uv build --no-sources`
verifies that wheel and source-distribution builds do not depend on
project-specific uv source overrides.

Issue #103 adds only the package scaffold and build configuration. Runtime
modules remain under `server/`, and existing commands continue to behave as
before. Its artifacts validate the build and installation boundary; they are
not the final distribution inventory.

## Incremental Module Migration

Follow these rules when a later Packaging issue moves a module:

1. Move the authoritative implementation into an appropriate module beneath
   `src/acquire/`.
2. Convert migrated code and its tests to explicit package-relative or
   `acquire.*` imports. Migrated modules and tests must not add `server/` to
   `sys.path`.
3. Preserve existing public behavior, protocols, persistence semantics, file
   formats, and command behavior. Packaging PRs do not perform behavioral
   refactors.
4. If an existing direct-file command or unmigrated caller still needs the old
   path, leave a minimal compatibility wrapper. A wrapper must not contain
   application logic, must identify the follow-up issue that removes it, and is
   not a second supported API.
5. Keep wrapper removal owned by
   [#111](https://github.com/sfelf/acquire/issues/111). Do not remove a wrapper
   until all callers use packaged modules or installed project scripts.
6. Update focused tests to import the packaged module and add a path-sensitive
   check when the migrated code reads assets, fixtures, configuration, or other
   files.
7. Do not edit generated client assets. Update their source or generation
   command only when the owning issue requires it.

Docker images install the project into a dedicated virtual environment and
invoke supported project scripts without `PYTHONPATH` or a `server/` working
directory. Issue #111 still owns removal of the compatibility wrappers
themselves.

Issue #105 moves the persistence boundary in reviewable slices. The ORM models
and session lifecycle are authoritative in `acquire.orm`; `server/orm.py`
temporarily aliases that same module object for unmigrated direct-file callers.
Authentication is authoritative in `acquire.auth`; `server/auth.py` provides
the equivalent temporary alias while the HTTP runtime remains under `server/`.
Database setup is authoritative in `acquire.setup_database`;
`server/setup_database.py` remains a temporary direct-file entry point only for
compatibility until issue #111. Docker and deployment callers use the installed
`acquire-setup-database` command, and Alembic is an operational runtime
dependency. Its
configuration, environment, revision template, and revision scripts are package
resources under `src/acquire/`, so the command works independently of the
repository and current working directory. The root `alembic.ini` remains a
developer-facing configuration that points to those same authoritative
packaged revisions. Issue #111 removes the transitional wrapper, and issue #127
owns the final artifact manifest closeout.

Issue #106 makes `acquire.game_server`, `acquire.realtime`, and
`acquire.http_server` authoritative for the game engine, WebSocket adapter, and
FastAPI app. The legacy files under `server/` delegate to those modules so
existing Docker, shell, and offline-tool paths continue to work until issues
#107, #110, and #111 migrate their respective callers. Static roots are
resolved explicitly from the shared `src/acquire/` source layout to
`client/main` and `client/stats`; this is the same layout used by editable
installs and the production image.

Issue #107 makes `acquire.log_tools`, `acquire.recreate_game`, and
`acquire.stats` authoritative for historical parsing and replay, snapshot
restoration, database log ingestion, ratings, and stats publication. Their
legacy files under `server/` remain minimal aliases or direct-file entry points
until issues #110 and #111 replace command paths and remove the wrappers. Stats
publication and staging roots use the former `client/stats/data` and
`server/stats_temp` locations when the package runs from the validated shared
source layout. Installed artifacts do not contain those directories, so
operators configure their absolute locations with `ACQUIRE_STATS_DATA_ROOT`
and `ACQUIRE_STATS_TEMP_ROOT`; relative configuration is rejected to prevent
working-directory-dependent writes. Stats generation creates missing staging
and per-user directories so newly attached empty volumes are supported.
Issue #110 exposes that continuous workflow as `acquire-update-stats`. The
command accepts explicit absolute `--stats-data-root` and
`--stats-temp-root` values, falls back to the corresponding environment
variables or validated source layout, validates configuration before database
initialization, and retries operational failures at the legacy interval with a
fixed diagnostic.

Issue #108 moves the retained MySQL backup importer and sanitized report
validator under `acquire.migration`. The migration package owns separate,
explicit legacy-source and current-target SQLAlchemy metadata, so importing it
does not load `acquire.orm` or create the application engine. Temporary
direct-file wrappers remain under `server/` until issues #109 and #111 replace
their callers and remove compatibility paths.

Issue #109 adds the installed `acquire-migrate-mysql-to-postgres` and
`acquire-validate-migration-reports` commands. The importer remains operational
only with the `mysql-migration` extra; the validator remains available in a
normal installation. Both commands run outside the repository, use stable
exit-code categories, and replace unsafe diagnostic values with fixed markers.
The compatibility wrappers remain until issue #111 removes the transitional
layout.

Issue #110 is delivered in three independently reviewable slices. The first
adds the installed database-setup boundary and packaged Alembic resources. The
second moves enum generation to `acquire.enumsgen`, adds
`acquire-generate-enums` and `acquire-update-stats`, and migrates the focused
npm and Compose enum callers. The final slice adds `acquire-http-server`,
installs the project in production and local images, and migrates the gateway
and remaining runtime callers.

### Gateway Command Boundary

| Field | Source and trust | Runtime use | Diagnostic policy |
| --- | --- | --- | --- |
| Host and port | Operator or container configuration, untrusted | Bind the Uvicorn listener | Validate the TCP port; use fixed invalid-argument output |
| Main and stats static roots | Operator or container configuration, private and untrusted | Serve generated external client assets | Require absolute existing directories before startup; never print |

`acquire-http-server` accepts `--host`, `--port`, `--main-static-root`, and
`--stats-static-root`. Invalid arguments exit 2; unavailable roots or listener
addresses exit 1 with a fixed marker before Uvicorn can reflect private values;
and a normal shutdown exits 0. Production and local containers pass both roots
explicitly and run from `/app`, not `/app/server`.

### Build And Maintenance Command Data Boundaries

| Field | Source and trust | Runtime use | Diagnostic policy |
| --- | --- | --- | --- |
| Client and release source roots | Operator or build configuration, private and untrusted | Discover JavaScript inputs for enum generation | Require absolute paths; never print |
| Replacement inputs and enum output path | Operator or build configuration, private and untrusted | Read or mutate the explicitly selected JavaScript files | Validate all replacement inputs first; use fixed failures |
| JavaScript source contents | Client source, untrusted text | Inspect normalized alphanumeric enum references only | Preserve legitimate enum names; never include source text in diagnostics |
| Stats publication and staging roots | Operator arguments or environment, private and untrusted | Stage and publish generated JSON/gzip files | Require absolute paths; never print |
| Database rows and log contents | Application database and logs, private and untrusted | Update persistence, ratings, records, and published stats | Never include values or exception representations in command diagnostics |

`acquire-generate-enums` exits with status 0 after generation or replacement,
status 2 for invalid arguments, and status 1 for missing inputs or operational
read/write failures. `acquire-update-stats` is continuous: invalid arguments
exit 2, invalid installed-layout configuration exits 1, update failures emit a
fixed marker and retry after 60 seconds, and interruption exits 130.

| Enum command state | Result |
| --- | --- |
| Development plus client root, optional output | Generate all enums; write stdout or the selected file; exit 0 |
| Release plus client and release roots, optional output | Generate referenced enums; write stdout or the selected file; exit 0 |
| Replace plus client root and one or more existing inputs | Validate every input, mutate selected files, exit 0 |
| Development with a release root, release without one, replace without inputs, or any relative path | Fixed invalid-argument diagnostic; exit 2 |
| Missing/unreadable input, unknown referenced enum, or write failure | Fixed operational diagnostic; exit 1 |

| Stats updater state | Result |
| --- | --- |
| New completed games | Commit log offsets and publish regenerated files, then wait |
| No completed-game changes | Commit updated offsets without publication, then wait |
| Database, staging, generation, publication, or unknown operational failure | Roll back the transaction, emit a fixed marker, clean remaining staged outputs where possible, then retry |
| Partial publication before a later move fails | Keep already published valid files, roll back offsets, clean remaining staging, and replace the full set on retry |
| Stale staged gzip files | Remove before compression; treat cleanup failure as retryable |
| Missing or relative installed-layout configuration | Emit a fixed configuration marker before database initialization; exit 1 |
| Process interruption | Stop without a traceback; exit 130 |

Issue #111 removes all transitional paths. Issue #127 then owns the final wheel
and source-distribution manifests and clean-wheel command verification.
