import json
import tomllib
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLIENT_ROOT = REPOSITORY_ROOT / "client"


def test_mysql_connector_is_isolated_to_backup_migration_extra() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert "mysql-connector-python>=9.3,<10" not in pyproject["project"]["dependencies"]
    assert pyproject["project"]["optional-dependencies"]["mysql-migration"] == [
        "mysql-connector-python>=9.3,<10"
    ]
    assert "mysql-connector-python>=9.3,<10" not in pyproject["dependency-groups"]["dev"]


def test_ci_verifies_runtime_and_mysql_migration_dependency_boundaries() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "uv run --isolated --frozen --no-dev python -" in workflow
    assert "import acquire.stats" in workflow
    assert "import acquire.http_server" in workflow
    assert 'assert importlib.util.find_spec("mysql") is None' in workflow
    assert (
        "uv run --isolated --frozen --no-dev --extra mysql-migration python -" in workflow
    )
    assert "import mysql.connector" in workflow
    assert "import acquire.migration.import_mysql_to_postgres" in workflow
    assert 'assert "acquire.orm" not in sys.modules' in workflow
    assert 'assert "trueskill" not in sys.modules' in workflow


def test_pyproject_defines_complete_direct_dependency_boundaries() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert set(pyproject["project"]["dependencies"]) == {
        "alembic>=1.17,<2",
        "fastapi>=0.115,<1",
        "psycopg[binary]>=3.2,<4",
        "sqlalchemy>=2,<3",
        "trueskill==0.4.4",
        "ujson>=5.13,<6",
        "uvicorn>=0.32,<1",
        "websockets>=14,<16",
    }
    assert pyproject["project"]["optional-dependencies"] == {
        "mysql-migration": ["mysql-connector-python>=9.3,<10"]
    }
    assert set(pyproject["dependency-groups"]["dev"]) == {
        "httpx>=0.27,<1",
        "mypy>=1.18,<2",
        "pre-commit>=4,<5",
        "pytest>=8.4,<9",
        "pytest-cov>=7,<8",
        "ruff>=0.14,<0.15",
    }


def test_uv_lock_records_project_dependency_boundaries() -> None:
    lock = tomllib.loads((REPOSITORY_ROOT / "uv.lock").read_text())
    acquire = next(package for package in lock["package"] if package["name"] == "acquire")
    runtime = acquire["dependencies"]
    optional = acquire["optional-dependencies"]
    development = acquire["dev-dependencies"]
    metadata = acquire["metadata"]

    assert {dependency["name"] for dependency in runtime} == {
        "alembic",
        "fastapi",
        "psycopg",
        "sqlalchemy",
        "trueskill",
        "ujson",
        "uvicorn",
        "websockets",
    }
    assert optional == {"mysql-migration": [{"name": "mysql-connector-python"}]}
    assert {dependency["name"] for dependency in development["dev"]} == {
        "httpx",
        "mypy",
        "pre-commit",
        "pytest",
        "pytest-cov",
        "ruff",
    }
    mysql_requirement = next(
        requirement
        for requirement in metadata["requires-dist"]
        if requirement["name"] == "mysql-connector-python"
    )
    assert mysql_requirement == {
        "name": "mysql-connector-python",
        "marker": "extra == 'mysql-migration'",
        "specifier": ">=9.3,<10",
    }


def test_dependabot_updates_uv_dependency_sources() -> None:
    config = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "dependabot.yml").read_text()
    )

    ecosystems = [update["package-ecosystem"] for update in config["updates"]]
    assert "pip" not in ecosystems
    assert ecosystems.count("uv") == 1

    uv_update = next(
        update for update in config["updates"] if update["package-ecosystem"] == "uv"
    )
    assert uv_update == {
        "package-ecosystem": "uv",
        "directory": "/",
        "schedule": {
            "interval": "weekly",
            "day": "monday",
            "time": "09:00",
            "timezone": "America/Los_Angeles",
        },
        "open-pull-requests-limit": 5,
        "labels": ["dependencies", "python"],
        "commit-message": {"prefix": "deps", "include": "scope"},
        "groups": {"python-dependencies": {"patterns": ["*"]}},
    }


def test_dependabot_updates_client_build_dependencies() -> None:
    config = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "dependabot.yml").read_text()
    )
    npm_updates = [
        update
        for update in config["updates"]
        if update["package-ecosystem"] == "npm"
    ]

    assert npm_updates == [
        {
            "package-ecosystem": "npm",
            "directory": "/client",
            "schedule": {
                "interval": "weekly",
                "day": "monday",
                "time": "09:00",
                "timezone": "America/Los_Angeles",
            },
            "open-pull-requests-limit": 5,
            "labels": ["dependencies", "javascript"],
            "commit-message": {"prefix": "deps", "include": "scope"},
            "groups": {"client-build-dependencies": {"patterns": ["*"]}},
        }
    ]


def test_dependency_docs_describe_single_uv_managed_boundary() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    agent_notes = (REPOSITORY_ROOT / "AGENTS.md").read_text()
    packaging_notes = (REPOSITORY_ROOT / "docs" / "packaging.md").read_text()

    assert "`pyproject.toml` declares all direct Python dependencies" in readme
    assert "`uv.lock` pins the\nreproducible resolved environment" in readme
    assert "`pyproject.toml` is the sole source of direct application dependencies" in (
        agent_notes
    )
    assert "`uv.lock` is the sole reproducible resolved Python dependency set" in (
        agent_notes
    )
    assert "## Python Dependency Boundary" in packaging_notes
    assert "`pyproject.toml` is the only direct Python dependency manifest" in (
        packaging_notes
    )
    assert "Dependabot uses its `uv`\necosystem support" in packaging_notes


def test_runtime_images_do_not_install_mysql_dependencies() -> None:
    local_dockerfile = (REPOSITORY_ROOT / "Dockerfile.local").read_text()
    production_dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text()

    assert "default-mysql-client" not in local_dockerfile
    assert "mysql-migration" not in production_dockerfile
    assert not (REPOSITORY_ROOT / "requirements.local-docker.txt").exists()


def test_local_docker_installs_project_outside_bind_mount() -> None:
    local_dockerfile = (REPOSITORY_ROOT / "Dockerfile.local").read_text()

    assert "UV_PROJECT_ENVIRONMENT=/opt/acquire" in local_dockerfile
    assert 'PATH="/opt/acquire/bin:$PATH"' in local_dockerfile
    assert "RUN uv sync --frozen --no-dev" in local_dockerfile
    assert "PYTHONPATH" not in local_dockerfile
    assert "requirements.local-docker.txt" not in local_dockerfile
    assert 'CMD ["acquire-http-server"' in local_dockerfile
    assert '"--main-static-root", "/app/client/main"' in local_dockerfile
    assert '"--stats-static-root", "/app/client/stats"' in local_dockerfile
    assert "server.py" not in local_dockerfile


def test_local_docker_includes_alembic_for_database_setup() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert "alembic>=1.17,<2" in pyproject["project"]["dependencies"]
    assert "alembic>=1.17,<2" not in pyproject["dependency-groups"]["dev"]
    assert pyproject["project"]["scripts"]["acquire-setup-database"] == (
        "acquire.setup_database:main"
    )


def test_local_docker_includes_postgres_driver_for_default_database() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert "psycopg[binary]>=3.2,<4" in pyproject["project"]["dependencies"]


def test_incremental_rating_dependency_stays_trueskill_compatible() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert "trueskill==0.4.4" in pyproject["project"]["dependencies"]
    assert not any(
        requirement.startswith("openskill")
        for requirement in pyproject["project"]["dependencies"]
    )


def test_client_build_uses_dart_sass_and_npm_scripts() -> None:
    package = json.loads((CLIENT_ROOT / "package.json").read_text())
    package_lock = json.loads((CLIENT_ROOT / "package-lock.json").read_text())
    dev_dependencies = package["devDependencies"]
    engines = package["engines"]
    scripts = package["scripts"]

    assert package["name"] == "acquire-client-assets"
    assert package["private"] is True
    assert engines == {"node": ">=22", "npm": ">=10"}
    assert set(dev_dependencies) == {"esbuild", "prettier", "sass"}
    assert "build:css" in scripts
    assert "build:enums" in scripts
    assert "build:js" in scripts
    assert scripts["build:enums"] == (
        "uv run --project .. --no-dev acquire-generate-enums js development "
        '--client-source-root "$PWD/main/js" '
        '--output "$PWD/main/js/enums.js"'
    )
    assert scripts["build:js"].startswith(
        "cd .. && client/node_modules/.bin/esbuild "
        "client/main/js/app.js --bundle"
    )
    assert scripts["build:client"] == (
        "npm run build:css && npm run build:enums && npm run build:js"
    )
    assert package_lock["name"] == "acquire-client-assets"
    assert (
        package_lock["packages"]["node_modules/sass"]["dependencies"]["immutable"]
        == "^5.1.5"
    )
    assert package_lock["packages"]["node_modules/immutable"]["version"] == "5.1.9"
    assert {
        "node_modules/clean-css",
        "node_modules/html-minifier",
        "node_modules/node-sass",
        "node_modules/uglify-js",
        "node_modules/webpack",
    }.isdisjoint(package_lock["packages"])


def test_client_manifest_owns_the_only_npm_dependency_boundary() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    agent_notes = (REPOSITORY_ROOT / "AGENTS.md").read_text()

    assert not (REPOSITORY_ROOT / "package.json").exists()
    assert not (REPOSITORY_ROOT / "package-lock.json").exists()
    assert (CLIENT_ROOT / "package.json").is_file()
    assert (CLIENT_ROOT / "package-lock.json").is_file()
    assert not (REPOSITORY_ROOT / "generate_client_files.sh").exists()
    assert "cd client\nnpm ci\nnpm run build:client" in readme
    assert "cd client\nnpm ci\nnpm run build:client" in agent_notes
    assert "Client assets and their npm manifests live under `client/`" in agent_notes


def test_supported_project_scripts_use_packaged_main_functions() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())
    scripts = pyproject["project"]["scripts"]

    assert scripts == {
        "acquire-generate-enums": "acquire.enumsgen:main",
        "acquire-http-server": "acquire.http_server:main",
        "acquire-migrate-mysql-to-postgres": (
            "acquire.migration.import_mysql_to_postgres:main"
        ),
        "acquire-setup-database": "acquire.setup_database:main",
        "acquire-update-stats": "acquire.stats:main",
        "acquire-validate-migration-reports": (
            "acquire.migration.validate_import_reports:main"
        ),
    }
    assert "acquire-game-server" not in scripts
    assert "acquire-log-tools" not in scripts


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

    assert "/node_modules" in gitignore
    assert "/client/node_modules" in gitignore
    assert "client/node_modules" in dockerignore
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
    assert "`client/package.json`" in asset_workflow
    assert "`client/package-lock.json`" in asset_workflow
    assert "three direct development dependencies" in asset_workflow
    assert "backend Python environment" in asset_workflow
    assert "legacy Node.js 6-era toolchain. Complete." in plans
    assert "build production assets in the\n     production Docker" in plans


def test_production_dockerfile_builds_client_assets_and_runs_python_gateway() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text()
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    deployment_notes = (REPOSITORY_ROOT / "docs" / "deployment.md").read_text()

    assert "FROM node:22-bookworm-slim AS client-assets" in dockerfile
    assert "ghcr.io/astral-sh/uv:0.11.22" in dockerfile
    assert "RUN uv sync --frozen --no-dev" in dockerfile
    assert "COPY src ./src" in dockerfile
    assert "server/enumsgen.py" not in dockerfile
    assert "COPY client/package.json client/package-lock.json ./client/" in dockerfile
    assert "RUN npm --prefix client ci" in dockerfile
    assert "RUN npm --prefix client run build:client" in dockerfile
    assert "FROM python:3.12-slim AS runtime" in dockerfile
    assert "UV_PROJECT_ENVIRONMENT=/opt/acquire" in dockerfile
    assert "RUN uv sync --frozen --no-dev --no-editable" in dockerfile
    assert "PYTHONPATH" not in dockerfile
    assert "requirements.local-docker.txt" not in dockerfile
    assert "client/main/js/main.js" in dockerfile
    assert "client/stats/css/stats.css" in dockerfile
    runtime_stage = dockerfile.split("FROM python:3.12-slim AS runtime", maxsplit=1)[1]
    assert "node_modules" not in runtime_stage
    assert "npm " not in runtime_stage
    assert 'CMD ["acquire-http-server"' in dockerfile
    assert '"--main-static-root", "/app/client/main"' in dockerfile
    assert '"--stats-static-root", "/app/client/stats"' in dockerfile
    assert "http_server.py" not in dockerfile
    assert "docker build -t acquire:production ." in readme
    assert "docker build -t acquire:production ." in deployment_notes
    assert "acquire-setup-database" in deployment_notes
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
    assert workflow.count("acquire-http-server --help") == 2
    assert workflow.count("assert '/opt/acquire/' in acquire.__file__") == 2
    assert workflow.count("Path('/app/client/main/js/main.js').is_file()") == 2
    assert workflow.count("Path('/app/client/main/css/main.css').is_file()") == 2
    assert workflow.count("Path('/app/client/stats/css/stats.css').is_file()") == 2
    assert "aws-actions/configure-aws-credentials@v4" in workflow
    assert "aws-actions/amazon-ecr-login@v2" in workflow
    assert "AWS_ROLE_TO_ASSUME" in workflow
    assert "AWS_ECR_REPOSITORY" in workflow
    assert "docker push" in workflow

    assert "GitHub Variables" in deployment_notes
    assert "AWS ECR Publishing Setup" in deployment_notes
    assert "AWS_ROLE_TO_ASSUME" in deployment_notes
    assert "AWS_ECR_REPOSITORY" in deployment_notes
    assert "sts:AssumeRoleWithWebIdentity" in deployment_notes
    assert "ecr:GetAuthorizationToken" in deployment_notes
    assert "ecr:PutImage" in deployment_notes
    assert "commit SHA" in deployment_notes

    trust_policy_text = deployment_notes.split("```json", 1)[1].split("```", 1)[0]
    trust_policy = json.loads(trust_policy_text)
    trust_statement = trust_policy["Statement"][0]
    assert trust_statement["Principal"]["Federated"] == (
        "arn:aws:iam::123456789012:"
        "oidc-provider/token.actions.githubusercontent.com"
    )
    assert trust_statement["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert trust_statement["Condition"]["StringEquals"] == {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": (
            "repo:sfelf/acquire:ref:refs/heads/main"
        ),
    }


def test_long_lived_delivery_configuration_targets_main() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    ci_workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text()
    production_workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "production-image.yml"
    ).read_text()
    deployment_notes = (REPOSITORY_ROOT / "docs" / "deployment.md").read_text()

    assert "badge.svg?branch=main" in readme
    assert "branch%3Amain" in readme
    assert "/branch/main/graph/badge.svg" in readme
    assert "/tree/main" in readme
    assert yaml.load(ci_workflow, Loader=yaml.BaseLoader)["on"]["push"]["branches"] == [
        "main"
    ]
    assert yaml.load(production_workflow, Loader=yaml.BaseLoader)["on"]["push"][
        "branches"
    ] == ["main"]
    assert "On pushes to `main`" in deployment_notes

    delivery_configuration = "\n".join(
        (readme, ci_workflow, production_workflow, deployment_notes)
    )
    assert "feature/modernization-refactor" not in delivery_configuration
    assert "feature%2Fmodernization-refactor" not in delivery_configuration


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

    assert override_by_module[("acquire.orm",)] == {"misc", "valid-type"}
    assert set(override_by_module) == {("acquire.orm",)}
