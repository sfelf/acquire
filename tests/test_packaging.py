import importlib
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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
    assert "find_spec('alembic') is None" in workflow_text
    assert "'site-packages' in Path(acquire.__file__).parts" in workflow_text
    assert "find_spec('mysql') is None" in workflow_text


def test_packaging_docs_define_incremental_module_migration_rules() -> None:
    packaging_notes = (REPOSITORY_ROOT / "docs" / "packaging.md").read_text()
    plan_notes = (REPOSITORY_ROOT / "PLANS.md").read_text()
    agent_notes = (REPOSITORY_ROOT / "AGENTS.md").read_text()
    normalized_packaging_notes = " ".join(packaging_notes.split())
    normalized_plan_notes = " ".join(plan_notes.split())

    assert "`src/acquire/`" in packaging_notes
    assert "must not contain application logic" in normalized_packaging_notes
    assert "`acquire.*` imports" in packaging_notes
    assert "must not add `server/` to `sys.path`" in normalized_packaging_notes
    assert "not the final distribution inventory" in normalized_packaging_notes
    assert "Issue #127 then owns the final wheel and source-distribution manifests" in (
        normalized_packaging_notes
    )
    assert "These are artifact-closeout requirements, not an instruction for #103" in (
        normalized_plan_notes
    )
    assert "docs/packaging.md" in agent_notes
