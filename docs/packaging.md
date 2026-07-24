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

Issue #111 owns the final wheel and source-distribution manifests after the
runtime modules and their tests have migrated into the installed-package
layout. It also owns final project scripts and removal of all transitional
paths.
