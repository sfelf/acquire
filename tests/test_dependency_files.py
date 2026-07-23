import json
import tomllib
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read_requirements(path: str) -> list[str]:
    return [
        line.strip()
        for line in (REPOSITORY_ROOT / path).read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_mysql_connector_is_isolated_to_backup_migration_extra() -> None:
    requirements = _read_requirements("requirements.txt")
    local_docker_requirements = _read_requirements("requirements.local-docker.txt")
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert "mysql-connector-python>=9.3,<10" not in requirements
    assert "mysql-connector-python>=9.3,<10" not in local_docker_requirements
    assert pyproject["project"]["optional-dependencies"]["mysql-migration"] == [
        "mysql-connector-python>=9.3,<10"
    ]
    assert "mysql-connector-python>=9.3,<10" not in pyproject["dependency-groups"]["dev"]


def test_ci_verifies_runtime_and_mysql_migration_dependency_boundaries() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "uv run --isolated --frozen --no-dev python -" in workflow
    assert "import cron" in workflow
    assert "import http_server" in workflow
    assert 'assert importlib.util.find_spec("mysql") is None' in workflow
    assert (
        "uv run --isolated --frozen --no-dev --extra mysql-migration python -" in workflow
    )
    assert "import mysql.connector" in workflow
    assert "import import_mysql_to_postgres" in workflow


def test_runtime_dependency_compatibility_pins_match_local_docker_baseline() -> None:
    requirements = set(_read_requirements("requirements.txt"))
    local_docker_requirements = set(_read_requirements("requirements.local-docker.txt"))
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    compatibility_requirements = {
        "psycopg[binary]>=3.2,<4",
        "six>=1.17,<2",
        "sqlalchemy>=2,<3",
        "ujson>=5.13,<6",
    }

    assert compatibility_requirements <= requirements
    assert compatibility_requirements <= local_docker_requirements
    assert {"psycopg[binary]>=3.2,<4", "sqlalchemy>=2,<3"} <= set(
        pyproject["project"]["dependencies"]
    )
    assert {"trueskill==0.4.4", "ujson>=5.13,<6"} <= set(
        pyproject["project"]["dependencies"]
    )
    assert {"six>=1.17,<2", "trueskill==0.4.4", "ujson>=5.13,<6"}.isdisjoint(
        pyproject["dependency-groups"]["dev"]
    )


def test_runtime_images_do_not_install_mysql_dependencies() -> None:
    local_dockerfile = (REPOSITORY_ROOT / "Dockerfile.local").read_text()
    production_dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text()
    local_docker_requirements = _read_requirements("requirements.local-docker.txt")

    assert "default-mysql-client" not in local_dockerfile
    assert "mysql-connector-python" not in local_docker_requirements
    assert "requirements.local-docker.txt" in production_dockerfile


def test_local_docker_includes_alembic_for_database_setup() -> None:
    local_docker_requirements = _read_requirements("requirements.local-docker.txt")

    assert "alembic>=1.17,<2" in local_docker_requirements


def test_local_docker_includes_postgres_driver_for_default_database() -> None:
    local_docker_requirements = _read_requirements("requirements.local-docker.txt")

    assert "psycopg[binary]>=3.2,<4" in local_docker_requirements


def test_incremental_rating_dependency_stays_trueskill_compatible() -> None:
    requirements = _read_requirements("requirements.txt")
    local_docker_requirements = _read_requirements("requirements.local-docker.txt")

    assert "trueskill==0.4.4" in requirements
    assert "trueskill==0.4.4" in local_docker_requirements
    assert not any(requirement.startswith("openskill") for requirement in requirements)
    assert not any(requirement.startswith("openskill") for requirement in local_docker_requirements)


def test_client_build_uses_dart_sass_and_npm_scripts() -> None:
    package = json.loads((REPOSITORY_ROOT / "package.json").read_text())
    package_lock = json.loads((REPOSITORY_ROOT / "package-lock.json").read_text())
    dev_dependencies = package["devDependencies"]
    engines = package["engines"]
    scripts = package["scripts"]

    assert engines == {"node": ">=22", "npm": ">=10"}
    assert "esbuild" in dev_dependencies
    assert "sass" in dev_dependencies
    assert "node-sass" not in dev_dependencies
    assert "webpack" not in dev_dependencies
    assert "build:css" in scripts
    assert "build:enums" in scripts
    assert "build:js" in scripts
    assert scripts["build:js"].startswith("esbuild client/main/js/app.js --bundle")
    assert scripts["build:client"] == (
        "npm run build:css && npm run build:enums && npm run build:js"
    )
    assert "node_modules/webpack" not in package_lock["packages"]


def test_client_asset_workflow_keeps_generated_outputs_untracked() -> None:
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text()
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text()
    plans = (REPOSITORY_ROOT / "PLANS.md").read_text()
    architecture_notes = (REPOSITORY_ROOT / "docs" / "architecture.md").read_text()
    local_development_notes = (
        REPOSITORY_ROOT / "docs" / "local-development.md"
    ).read_text()
    asset_workflow = (REPOSITORY_ROOT / "docs" / "client-assets.md").read_text()

    generated_assets = {
        "client/main/css/main.css",
        "client/main/js/enums.js",
        "client/main/js/main.js",
        "client/stats/css/stats.css",
    }

    for asset in generated_assets:
        assert f"/{asset}" in gitignore
        assert asset in dockerignore

    assert "Client Asset Workflow" in asset_workflow
    assert "Do not commit generated client assets" in asset_workflow
    assert "npm run build:client" in asset_workflow
    assert "docker compose --profile client-build run --rm client-assets" in (
        asset_workflow
    )
    assert "The production Dockerfile builds client assets" in asset_workflow
    assert "docs/deployment.md" in asset_workflow
    assert "docs/client-assets.md" in architecture_notes
    assert "docs/client-assets.md" in local_development_notes
    assert "legacy Node.js 6-era toolchain. Complete." in plans
    assert "build production assets in the\n     production Docker" in plans


def test_production_dockerfile_builds_client_assets_and_runs_python_gateway() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text()
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    deployment_notes = (REPOSITORY_ROOT / "docs" / "deployment.md").read_text()

    assert "FROM node:22-bookworm-slim AS client-assets" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build:client" in dockerfile
    assert "FROM python:3.12-slim AS runtime" in dockerfile
    assert "COPY requirements.local-docker.txt ." in dockerfile
    assert "client/main/js/main.js" in dockerfile
    assert "client/stats/css/stats.css" in dockerfile
    assert 'CMD ["python", "http_server.py", "--host", "0.0.0.0", "--port", "9000"]' in (
        dockerfile
    )
    assert "docker build -t acquire:production ." in readme
    assert "docker build -t acquire:production ." in deployment_notes
    assert "python setup_database.py" in deployment_notes
    assert "AWS" in deployment_notes


def test_production_image_workflow_builds_and_optionally_publishes_to_ecr() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "production-image.yml").read_text()
    workflow_data = yaml.safe_load(workflow)
    deployment_notes = (REPOSITORY_ROOT / "docs" / "deployment.md").read_text()
    build_job = workflow_data["jobs"]["build"]
    publish_job = workflow_data["jobs"]["publish-ecr"]

    assert {"build", "publish-ecr"} <= set(workflow_data["jobs"])
    assert build_job.get("permissions") in (None, {"contents": "read"})
    assert publish_job["permissions"] == {"contents": "read", "id-token": "write"}
    assert "docker build -t acquire:production-test ." in workflow
    assert workflow.count("production image smoke ok") == 2
    assert "aws-actions/configure-aws-credentials@v4" in workflow
    assert "aws-actions/amazon-ecr-login@v2" in workflow
    assert "AWS_ROLE_TO_ASSUME" in workflow
    assert "AWS_ECR_REPOSITORY" in workflow
    assert "docker push" in workflow

    assert "GitHub Variables" in deployment_notes
    assert "AWS ECR Publishing Setup" in deployment_notes
    assert "AWS_ROLE_TO_ASSUME" in deployment_notes
    assert "AWS_ECR_REPOSITORY" in deployment_notes
    assert "token.actions.githubusercontent.com" in deployment_notes
    assert "sts:AssumeRoleWithWebIdentity" in deployment_notes
    assert "ecr:GetAuthorizationToken" in deployment_notes
    assert "ecr:PutImage" in deployment_notes
    assert "repo:sfelf/acquire:ref:refs/heads/main" in deployment_notes
    assert "repo:sfelf/acquire:ref:refs/heads/feature/modernization-refactor" in (
        deployment_notes
    )
    assert "commit SHA" in deployment_notes


def test_python_quality_config_scopes_type_checker_exceptions() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())
    mypy_config = pyproject["tool"]["mypy"]
    mypy_overrides = pyproject["tool"]["mypy"]["overrides"]
    ruff_rules = pyproject["tool"]["ruff"]["lint"]["select"]

    assert "disable_error_code" not in mypy_config
    assert {
        "A",
        "COM818",
        "COM819",
        "ICN",
        "ISC",
        "PIE",
        "RSE",
        "RUF021",
    }.issubset(ruff_rules)

    override_by_module = {
        tuple(override["module"]): set(override["disable_error_code"])
        for override in mypy_overrides
    }

    assert override_by_module[("orm",)] == {"misc", "valid-type"}
    assert set(override_by_module) == {("orm",)}
