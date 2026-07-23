# Client Asset Workflow

Client CSS, generated enum JavaScript, and the browser JavaScript bundle are
build outputs. They stay gitignored in the repository so source changes remain
reviewable and generated diffs do not obscure runtime changes.

## Source Files

- `client/main/css/main.scss` and `client/stats/css/stats.scss` are compiled by
  Dart Sass.
- `server/enumsgen.py` generates `client/main/js/enums.js` from the Python enum
  definitions.
- `client/main/js/app.js` is the browser JavaScript entrypoint. esbuild bundles
  that entrypoint and its CommonJS dependencies into `client/main/js/main.js`.

## Local Builds

Build all client assets from the host with:

```bash
npm ci
npm run build:client
```

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

The separately gitignored `client/stats/data` directory is runtime data, not a
client build output. The cron log processor publishes ratings and per-user JSON
there, and the Python gateway serves it at `/stats/data/`. Deployments that run
cron and the gateway as separate processes must give both processes access to
the same writable `client/stats/data` tree.

## Repository Boundary

Do not commit generated client assets. The tracked source of truth is the SCSS,
JavaScript source modules, Python enum generator, `package.json`, and
`package-lock.json`.

The default local Python gateway intentionally checks for generated assets at
startup and tells the developer to run the client build helper when they are
missing. Docker Compose bind-mounts the checkout in local development, so the
helper can generate assets once without making the running gateway depend on the
Node container.

## Deployment Packaging

The production Dockerfile builds client assets in a dedicated Node 22 image
stage, then copies the generated files into the Python runtime image before
starting the gateway. See `docs/deployment.md` for the production image build
and runtime commands.
