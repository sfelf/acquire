# Deployment

The production Docker image packages the Python FastAPI gateway with generated
browser assets. It is the deployable artifact for container hosts such as AWS,
Render, or any service that can run a standard Docker image.

## Build The Image

Build from the repository root:

```bash
docker build -t acquire:production .
```

The Dockerfile uses a Node 22 build stage for `npm run build:client`, then
copies the generated CSS, enum JavaScript, and browser bundle into a slim Python
runtime stage. Generated client assets stay untracked in git.

## Configure The Database

Production deployments should provide an explicit Postgres URL:

```env
ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/acquire
```

The image still contains MySQL-compatible dependencies while the production
cutover and rollback gates remain open, but Postgres is the expected deployment
target for new environments.

## Apply Migrations

Run migrations before starting or releasing the web process:

```bash
docker run --rm \
  -e ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/acquire \
  acquire:production \
  python setup_database.py
```

`server/setup_database.py` applies Alembic migrations and required lookup data
without dropping existing data.

## Run The Gateway

Start the web process:

```bash
docker run --rm \
  -p 9000:9000 \
  -e ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/acquire \
  acquire:production
```

The container listens on port `9000` and exposes the same `/sockjs/info`
healthcheck used by local Docker.

## AWS Path

The image can be pushed to Amazon ECR and run on ECS Fargate, App Runner, or
another container service. Before production traffic moves to Postgres, complete
the backup rehearsal and rollback gates in `docs/database.md` and
`docs/postgres-backup-rehearsal.md`.
