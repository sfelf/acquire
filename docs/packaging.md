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

Until issue #111 removes legacy direct-file working directories, Docker images
temporarily add `/app/src` to `PYTHONPATH` so those commands can import migrated
modules. This is compatibility scaffolding, not an alternative package layout.

Issue #105 moves the persistence boundary in reviewable slices. The ORM models
and session lifecycle are authoritative in `acquire.orm`; `server/orm.py`
temporarily aliases that same module object for unmigrated direct-file callers.
Authentication is authoritative in `acquire.auth`; `server/auth.py` provides
the equivalent temporary alias while the HTTP runtime remains under `server/`.
Database setup is authoritative in `acquire.setup_database`;
`server/setup_database.py` remains a temporary direct-file entry point for
Docker and deployment callers until issue #110 replaces those calls with an
installed project script. Built artifacts can import the setup module without
development dependencies, but running setup remains limited to repository
environments that install Alembic while its configuration and migrations remain
repository resources. Issue #110 owns the installed command and issue #111 owns
the final artifact resource layout.
Alembic imports the packaged metadata directly and resolves its migration
directory relative to `alembic.ini`, independent of the current working
directory. Issue #111 removes the alias after every runtime and command path is
packaged.

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

Issue #108 moves the retained MySQL backup importer and sanitized report
validator under `acquire.migration`. The migration package owns separate,
explicit legacy-source and current-target SQLAlchemy metadata, so importing it
does not load `acquire.orm` or create the application engine. Temporary
direct-file wrappers remain under `server/` until issues #109 and #111 replace
their callers and remove compatibility paths.

Issue #111 owns the final wheel and source-distribution manifests after the
runtime modules and their tests have migrated into the installed-package
layout. It also owns final project scripts and removal of all transitional
paths.
