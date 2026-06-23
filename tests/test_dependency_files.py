import json
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read_requirements(path: str) -> list[str]:
    return [
        line.strip()
        for line in (REPOSITORY_ROOT / path).read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_runtime_requirements_use_reachable_mysql_connector_package() -> None:
    requirements = _read_requirements("requirements.txt")

    assert "mysql-connector-python>=9.3,<10" in requirements
    assert not any(requirement.startswith("http://cdn.mysql.com/") for requirement in requirements)


def test_runtime_dependency_compatibility_pins_match_local_docker_baseline() -> None:
    requirements = set(_read_requirements("requirements.txt"))
    local_docker_requirements = set(_read_requirements("requirements.local-docker.txt"))

    compatibility_requirements = {
        "mysql-connector-python>=9.3,<10",
        "six>=1.17,<2",
        "sqlalchemy>=2,<3",
        "ujson>=5.13,<6",
    }

    assert compatibility_requirements <= requirements
    assert compatibility_requirements <= local_docker_requirements


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
    assert "Production Docker and AWS packaging should build client assets" in (
        asset_workflow
    )
    assert "docs/client-assets.md" in architecture_notes
    assert "docs/client-assets.md" in local_development_notes
    assert "legacy Node.js 6-era toolchain. Complete." in plans
    assert "build production assets in the\n     production Docker" in plans


def test_python_quality_config_scopes_type_checker_exceptions() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())
    mypy_config = pyproject["tool"]["mypy"]
    mypy_overrides = pyproject["tool"]["mypy"]["overrides"]
    ruff_rules = pyproject["tool"]["ruff"]["lint"]["select"]

    assert "disable_error_code" not in mypy_config
    assert "RUF021" in ruff_rules

    override_by_module = {
        tuple(override["module"]): set(override["disable_error_code"])
        for override in mypy_overrides
    }

    assert override_by_module[("orm",)] == {"misc", "valid-type"}
    assert override_by_module[("server",)] == {
        "arg-type",
        "assignment",
        "misc",
        "operator",
        "union-attr",
        "var-annotated",
    }
