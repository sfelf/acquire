# Client Asset Workflow

Client CSS, generated enum JavaScript, and the browser JavaScript bundle are
build outputs. They stay gitignored in the repository so source changes remain
reviewable and generated diffs do not obscure runtime changes.

## Source Files

- `client/main/css/main.scss` and `client/stats/css/stats.scss` are compiled by
  Dart Sass.
- `acquire-generate-enums` generates `client/main/js/enums.js` through the
  packaged `acquire.enumsgen` module and canonical definitions in
  `src/acquire/enums.py`.
- `client/main/js/app.js` is the browser JavaScript entrypoint. esbuild bundles
  that entrypoint and its CommonJS dependencies into `client/main/js/main.js`.

The npm manifests live alongside these browser sources under `client/`. Their
three direct development dependencies have one build-only owner each:

| Dependency | Responsibility |
| --- | --- |
| Dart Sass (`sass`) | Compile the main and stats SCSS entrypoints |
| esbuild | Bundle browser JavaScript and emit its source map |
| Prettier | Provide the explicit client-source formatting command |

None of these packages is installed in the backend Python environment or the
production image's final runtime stage.

## Local Builds

Build all client assets from the host with:

```bash
cd client
npm ci
npm run build:client
npm run verify:client
```

The supported host and CI toolchain is Node.js 22 with npm 10 or newer.
`verify:client` is read-only and fails after reporting every missing or empty
expected output. Its focused Node test covers each output independently.

Format the maintained client source tree with:

```bash
npm --prefix client run format
```

Check the same formatting baseline without modifying files with:

```bash
npm --prefix client run format:check
```

CI runs the read-only check after installing the locked client tooling and
before building generated assets.

Build them through Docker Compose with:

```bash
docker compose --profile client-build run --rm client-assets
```

Both paths write the same gitignored files into the checkout:

- `client/main/css/main.css`
- `client/stats/css/stats.css`
- `client/main/js/enums.js`
- `client/main/js/main.js`
- `client/main/js/main.js.map`

The Compose helper runs the same CSS, JavaScript, and verification scripts
after the packaged Python enum helper completes. The Python gateway checks the
same five-file output set before it starts.

The npm enum command runs the installed project script through the parent
uv-managed Python project with explicit absolute client-source and output
paths. npm resolves only `client/package-lock.json`. The Compose enum helper
invokes the same installed command with `/app/client/main/js`.

Run development generation directly with:

```bash
uv run --no-dev acquire-generate-enums js development \
  --client-source-root "$PWD/client/main/js" \
  --output "$PWD/client/main/js/enums.js"
```

Release generation additionally requires an absolute
`--release-source-root`. Omit `--output` to write generated module text to
stdout. The `replace` operation accepts one or more absolute JavaScript input
files after `--client-source-root`; it validates every input before modifying
any file.

The separately gitignored `client/stats/data` directory is runtime data, not a
client build output. `acquire-update-stats` publishes ratings and per-user JSON
there, and the Python gateway serves it at `/stats/data/`. Deployments that run
the updater and gateway as separate processes must give both processes access
to the same writable publication tree.

## Repository Boundary

Do not commit generated client assets. The tracked source of truth is the SCSS,
JavaScript source modules, Python enum generator, `client/package.json`, and
`client/package-lock.json`.

The default local Python gateway intentionally checks for generated assets at
startup and tells the developer to run the client build helper when they are
missing. Docker Compose bind-mounts the checkout in local development, so the
helper can generate assets once without making the running gateway depend on the
Node container.

## Deployment Packaging

The production Dockerfile builds and verifies client assets in a dedicated
Node 22 image stage, then copies the generated files into the Python runtime
image before starting the gateway. CI confirms the final image contains all
five outputs but no Node executable, npm executable, or `node_modules`. See
`docs/deployment.md` for the production image build and runtime commands.
