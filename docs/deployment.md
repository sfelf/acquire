# Deployment

The production Docker image packages the Python FastAPI gateway with generated
browser assets. It is the deployable artifact for container hosts such as AWS,
Render, or any service that can run a standard Docker image.

## Build The Image

Build from the repository root:

```bash
docker build -t acquire:production .
```

The Dockerfile installs `client/package-lock.json` in a Node 22 build stage and
runs the client manifest's `build:client` and `verify:client` scripts, then
copies the generated CSS, enum JavaScript, browser bundle, and source map into a
slim Python runtime stage. Node, npm, and `node_modules` do not enter the final
runtime stage. CI smoke-tests the complete five-file output set and the absence
of those Node runtime tools. Generated client assets stay untracked in git.

The standalone Python wheel is a runtime-code artifact, not a complete browser
deployment: it deliberately excludes generated client assets. Deployments that
install the wheel directly must build or supply separate main and stats asset
trees, then pass their absolute paths through `--main-static-root` and
`--stats-static-root`. See `docs/packaging.md` for the exact distribution
inventory and clean-install verification command.

## Configure The Database

Production deployments should provide an explicit Postgres URL:

```env
ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/acquire
```

The image installs only the Postgres application runtime. The optional MySQL
driver used by the backup import tool is not included.

## Apply Migrations

Run migrations before starting or releasing the web process:

```bash
docker run --rm \
  -e ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/acquire \
  acquire:production \
  acquire-setup-database
```

`acquire-setup-database` applies packaged Alembic migrations and required
lookup data without dropping existing data.

## Run The Gateway

Start the web process:

```bash
docker run --rm \
  -p 9000:9000 \
  -e ACQUIRE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/acquire \
  acquire:production
```

The container starts through `acquire-http-server`, listens on port `9000`,
and passes explicit `/app/client/main` and `/app/client/stats` roots. It exposes
the same `/sockjs/info` healthcheck used by local Docker.

## AWS Path

The image can be pushed to Amazon ECR and run on ECS Fargate, App Runner, or
another container service. The `Production Image` GitHub Actions workflow always
builds and smoke-tests the production image. On pushes to `main`, it can also
publish the image to ECR when the repository has these GitHub Actions variables
configured:

- `AWS_REGION`: AWS region that contains the target ECR repository.
- `AWS_ROLE_TO_ASSUME`: IAM role ARN trusted by GitHub Actions OIDC.
- `AWS_ECR_REPOSITORY`: ECR repository name for the production image.

The pushed image tag is the commit SHA. Deployment systems should promote an
explicit SHA tag rather than relying on mutable local image names.

### GitHub Variables

Configure these as repository variables under GitHub repository settings:
`Secrets and variables`, `Actions`, `Variables`.

- `AWS_REGION`: AWS region for the ECR repository, such as `us-east-1`.
- `AWS_ROLE_TO_ASSUME`: IAM role ARN that GitHub Actions can assume through
  OIDC, such as
  `arn:aws:iam::123456789012:role/acquire-github-actions-ecr-publisher`.
- `AWS_ECR_REPOSITORY`: ECR repository name for the production image, such as
  `acquire`.

These are variables rather than secrets because they are deployment identifiers,
not credentials. The workflow receives short-lived AWS credentials only after
AWS validates the GitHub OIDC token against the IAM role trust policy.

### AWS ECR Publishing Setup

Create an ECR repository whose name matches `AWS_ECR_REPOSITORY`.

Create or reuse an IAM OIDC provider for GitHub Actions:

- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

Create an IAM role for publishing with a trust policy scoped to this repository
and the branches that are allowed to publish:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:sfelf/acquire:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

Attach an ECR push policy to that role. Scope repository permissions to the
specific ECR repository ARN and keep `ecr:GetAuthorizationToken` on `*`, as AWS
requires:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:CompleteLayerUpload",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      "Resource": "arn:aws:ecr:us-east-1:123456789012:repository/acquire"
    },
    {
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    }
  ]
}
```

After this is configured, a merge or direct push to an allowed branch builds,
smoke-tests, tags, and pushes the image as:

```text
123456789012.dkr.ecr.us-east-1.amazonaws.com/acquire:<commit-sha>
```

Before production traffic moves to Postgres, complete the backup rehearsal and
rollback gates in `docs/database.md` and `docs/postgres-backup-rehearsal.md`.
