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

## Repository Boundary

Do not commit generated client assets. The tracked source of truth is the SCSS,
JavaScript source modules, Python enum generator, `package.json`, and
`package-lock.json`.

The default local Python gateway intentionally checks for generated assets at
startup and tells the developer to run the client build helper when they are
missing. Docker Compose bind-mounts the checkout in local development, so the
helper can generate assets once without making the running gateway depend on the
Node container.

## Deployment Follow-Up

Production Docker and AWS packaging should build client assets in a dedicated
image stage or release artifact workflow before starting the Python gateway.
That packaging decision belongs with the production deployment work rather than
the local development helper.
