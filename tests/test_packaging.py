import ast
import importlib
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEGACY_MODULE_NAMES = {
    "auth",
    "cron",
    "enums",
    "enumsgen",
    "http_server",
    "import_mysql_to_postgres",
    "logs_to_games",
    "orm",
    "recreate_game",
    "server",
    "settings",
    "setup_database",
    "username_to_user_id",
    "util",
    "validate_import_reports",
    "websocket_gateway",
}


def test_project_uses_bounded_uv_build_backend() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert pyproject["build-system"] == {
        "requires": ["uv_build>=0.11.22,<0.12"],
        "build-backend": "uv_build",
    }
    assert pyproject.get("tool", {}).get("uv", {}).get("package") is not False


def test_acquire_package_imports_from_src_layout() -> None:
    acquire = importlib.import_module("acquire")

    assert Path(acquire.__file__).resolve() == (
        REPOSITORY_ROOT / "src" / "acquire" / "__init__.py"
    ).resolve()


def test_unsupported_direct_module_commands_are_retired() -> None:
    game_server = importlib.import_module("acquire.game_server")
    log_tools = importlib.import_module("acquire.log_tools")

    assert not hasattr(game_server, "main")
    assert not hasattr(log_tools, "main")


def test_ci_builds_package_across_supported_python_versions() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
    workflow_text = workflow_path.read_text()
    workflow = yaml.safe_load(workflow_text)

    assert workflow["jobs"]["python"]["strategy"]["matrix"]["python-version"] == [
        "3.12",
        "3.13",
        "3.14",
    ]
    assert 'uv run python -c "import acquire"' in workflow_text
    assert "uv build --no-sources" in workflow_text
    assert 'artifacts=("$GITHUB_WORKSPACE"/dist/*)' in workflow_text
    assert 'test "${#artifacts[@]}" -eq 2' in workflow_text
    assert 'cd "$artifact_test_dir"' in workflow_text
    assert 'uv venv --python "${{ matrix.python-version }}"' in workflow_text
    assert 'uv pip install --python "$artifact_test_dir/.venv/bin/python"' in workflow_text
    assert '"$artifact"' in workflow_text
    assert '--no-deps "$artifact"' not in workflow_text
    assert ".venv/bin/python -c" in workflow_text
    assert "import acquire.auth" in workflow_text
    assert "import acquire.enums" in workflow_text
    assert "import acquire.enumsgen" in workflow_text
    assert "import acquire.game_server" in workflow_text
    assert "import acquire.http_server" in workflow_text
    assert "import acquire.log_tools" in workflow_text
    assert "import acquire.orm" in workflow_text
    assert "import acquire.realtime" in workflow_text
    assert "import acquire.recreate_game" in workflow_text
    assert "import acquire.settings" in workflow_text
    assert "import acquire.setup_database" in workflow_text
    assert "import acquire.stats" in workflow_text
    assert "import acquire.username_to_user_id" in workflow_text
    assert "import acquire.util" in workflow_text
    assert "find_spec('alembic') is not None" in workflow_text
    assert "'site-packages' in Path(acquire.__file__).parts" in workflow_text
    assert "find_spec('mysql') is None" in workflow_text
    assert "package_root.joinpath('alembic.ini').is_file()" in workflow_text
    assert "package_root.joinpath('migrations', 'env.py').is_file()" in workflow_text
    assert ".venv/bin/acquire-setup-database --help" in workflow_text
    assert ".venv/bin/acquire-generate-enums --help" in workflow_text
    assert ".venv/bin/acquire-http-server --help" in workflow_text
    assert ".venv/bin/acquire-update-stats --help" in workflow_text


def test_server_compatibility_layout_is_removed() -> None:
    assert not list((REPOSITORY_ROOT / "server").glob("*.py"))

    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())
    assert pyproject["tool"]["coverage"]["run"]["source"] == ["src/acquire"]
    assert pyproject["tool"]["mypy"]["files"] == ["src/acquire"]

    conftest = (REPOSITORY_ROOT / "tests" / "conftest.py").read_text()
    assert "SERVER_DIR" not in conftest
    assert "sys.path.insert" not in conftest


def test_active_workflows_have_no_legacy_server_path_configuration() -> None:
    active_paths = (
        REPOSITORY_ROOT / "Dockerfile",
        REPOSITORY_ROOT / "Dockerfile.local",
        REPOSITORY_ROOT / "docker-compose.yml",
        REPOSITORY_ROOT / "docker-compose.test.yml",
        REPOSITORY_ROOT / "package.json",
        REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "production-image.yml",
    )
    legacy_files = (
        "cron.py",
        "enumsgen.py",
        "http_server.py",
        "import_mysql_to_postgres.py",
        "logs_to_games.py",
        "server.py",
        "setup_database.py",
        "validate_import_reports.py",
    )

    for active_path in active_paths:
        content = active_path.read_text()
        assert "PYTHONPATH=" not in content, active_path
        assert "PYTHONPATH:" not in content, active_path
        for legacy_file in legacy_files:
            assert f"server/{legacy_file}" not in content, active_path


def test_python_imports_use_the_acquire_package_boundary() -> None:
    source_roots = (
        REPOSITORY_ROOT / "src",
        REPOSITORY_ROOT / "tests",
    )
    for source_root in source_roots:
        for source_path in source_root.rglob("*.py"):
            tree = ast.parse(source_path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots = {alias.name.split(".", 1)[0] for alias in node.names}
                    assert not imported_roots & LEGACY_MODULE_NAMES, source_path
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    assert node.module.split(".", 1)[0] not in LEGACY_MODULE_NAMES, (
                        source_path
                    )


def test_packaging_docs_define_completed_source_layout() -> None:
    packaging_notes = (REPOSITORY_ROOT / "docs" / "packaging.md").read_text()
    plan_notes = (REPOSITORY_ROOT / "PLANS.md").read_text()
    agent_notes = (REPOSITORY_ROOT / "AGENTS.md").read_text()
    normalized_packaging_notes = " ".join(packaging_notes.split())
    normalized_plan_notes = " ".join(plan_notes.split())

    assert "`src/acquire/`" in packaging_notes
    assert "`acquire.*` imports" in packaging_notes
    assert "sole production Python source boundary" in normalized_packaging_notes
    assert "exactly six supported project scripts" in normalized_packaging_notes
    assert "Issue [#127]" in normalized_packaging_notes
    assert "artifact closeout" in normalized_plan_notes
    assert "docs/packaging.md" in agent_notes
