import ast
import importlib
import re
import runpy
import stat
import subprocess
import sys
import tarfile
import tomllib
import zipfile
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
    assert "uv run python scripts/verify_distribution.py" in workflow_text


def test_uv_build_manifest_policy_matches_distribution_contract() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert pyproject["tool"]["uv"]["build-backend"] == {
        "source-include": ["tests/**"],
        "source-exclude": [
            "/.coverage",
            "/.env",
            "/.github",
            "/client",
            "/coverage.json",
            "/coverage.xml",
            "/dist",
            "/docs",
            "/lib",
            "/node_modules",
            "/scripts",
            "/stats_temp",
            "/uv.lock",
        ],
    }


def test_distribution_verifier_checks_survive_python_optimization() -> None:
    verifier_path = REPOSITORY_ROOT / "scripts" / "verify_distribution.py"
    verifier_source = verifier_path.read_text()
    verifier_tree = ast.parse(verifier_source)

    assert not any(isinstance(node, ast.Assert) for node in ast.walk(verifier_tree))
    assert not any(
        re.search(r"\bassert\b", node.value)
        for node in ast.walk(verifier_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )
    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            (
                "import runpy; "
                f"namespace = runpy.run_path({str(verifier_path)!r}, "
                "run_name='distribution_verifier_test'); "
                "require = namespace['require']; "
                "error = namespace['VerificationError']; "
                "\ntry:\n"
                "    require(False, 'optimization-safe')\n"
                "except error as exc:\n"
                "    if str(exc) != 'optimization-safe':\n"
                "        raise\n"
                "else:\n"
                "    raise RuntimeError('verification check was disabled')\n"
            ),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_distribution_verifier_rejects_duplicate_wheel_members(
    tmp_path: Path,
) -> None:
    verifier = runpy.run_path(
        REPOSITORY_ROOT / "scripts" / "verify_distribution.py",
        run_name="distribution_verifier_test",
    )
    wheel = tmp_path / "duplicate.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("acquire/__init__.py", "first")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("acquire/__init__.py", "second")

    with pytest.raises(
        verifier["VerificationError"],
        match="wheel contains duplicate member names",
    ):
        verifier["wheel_manifest"](wheel)


def test_distribution_verifier_rejects_duplicate_sdist_members(
    tmp_path: Path,
) -> None:
    verifier = runpy.run_path(
        REPOSITORY_ROOT / "scripts" / "verify_distribution.py",
        run_name="distribution_verifier_test",
    )
    sdist = tmp_path / "duplicate.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        member = tarfile.TarInfo("acquire-0.1.0/README.md")
        archive.addfile(member)
        archive.addfile(member)

    with pytest.raises(
        verifier["VerificationError"],
        match="source distribution contains duplicate member names",
    ):
        verifier["sdist_manifest"](sdist)


def test_distribution_verifier_rejects_sdist_links(tmp_path: Path) -> None:
    verifier = runpy.run_path(
        REPOSITORY_ROOT / "scripts" / "verify_distribution.py",
        run_name="distribution_verifier_test",
    )
    sdist = tmp_path / "link.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        member = tarfile.TarInfo("acquire-0.1.0/src/acquire/linked.py")
        member.type = tarfile.SYMTYPE
        member.linkname = "__init__.py"
        archive.addfile(member)

    with pytest.raises(
        verifier["VerificationError"],
        match="source distribution contains an unsupported member type",
    ):
        verifier["sdist_manifest"](sdist)


def test_distribution_verifier_rejects_wheel_links(tmp_path: Path) -> None:
    verifier = runpy.run_path(
        REPOSITORY_ROOT / "scripts" / "verify_distribution.py",
        run_name="distribution_verifier_test",
    )
    wheel = tmp_path / "link.whl"
    member = zipfile.ZipInfo("acquire/linked.py")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(member, "__init__.py")

    with pytest.raises(
        verifier["VerificationError"],
        match="wheel contains an unsupported member type",
    ):
        verifier["wheel_manifest"](wheel)


def test_distribution_verifier_removes_all_command_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = runpy.run_path(
        REPOSITORY_ROOT / "scripts" / "verify_distribution.py",
        run_name="distribution_verifier_test",
    )
    sanitized_variables = {
        "PYTHONPATH",
        "ACQUIRE_ARTIFACT_POSTGRES_URL",
        "ACQUIRE_DATABASE_URL",
        "ACQUIRE_STATS_DATA_ROOT",
        "ACQUIRE_STATS_TEMP_ROOT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
    }
    assert set(verifier["SANITIZED_ENVIRONMENT_VARIABLES"]) == sanitized_variables
    for variable in sanitized_variables:
        monkeypatch.setenv(variable, "private-secret")
    monkeypatch.setenv("ACQUIRE_VERIFY_SENTINEL", "preserved")

    environment = verifier["clean_environment"]()

    assert sanitized_variables.isdisjoint(environment)
    assert environment["ACQUIRE_VERIFY_SENTINEL"] == "preserved"


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
    assert "Distribution Artifact Contract" in packaging_notes
    assert "inventory contract" in normalized_packaging_notes
    assert "scripts/verify_distribution.py" in packaging_notes
    assert "Packaging milestone is complete" in normalized_plan_notes
    assert "Issue #127 defines and verifies" in normalized_plan_notes
    assert "docs/packaging.md" in agent_notes
    assert "completed source-layout, distribution" in " ".join(agent_notes.split())
