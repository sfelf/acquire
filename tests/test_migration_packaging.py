"""Verify the packaged MySQL backup-migration boundary."""

import ast
import importlib
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_MODULES = {
    "import_mysql_to_postgres": "import_mysql_to_postgres",
    "validate_import_reports": "validate_import_reports",
}
MIGRATION_COMMANDS = {
    "acquire-migrate-mysql-to-postgres": (
        "acquire.migration.import_mysql_to_postgres:main"
    ),
    "acquire-validate-migration-reports": (
        "acquire.migration.validate_import_reports:main"
    ),
}


def test_migration_project_scripts_remain_in_the_supported_command_contract() -> None:
    """Verify package metadata retains the issue-owned migration commands."""
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert MIGRATION_COMMANDS.items() <= pyproject["project"]["scripts"].items()


@pytest.mark.parametrize(("package_name", "legacy_name"), MIGRATION_MODULES.items())
def test_packaged_migration_module_is_authoritative_and_legacy_module_is_alias(
    package_name: str,
    legacy_name: str,
) -> None:
    """Verify each legacy migration path shares its packaged module object."""
    package_module = importlib.import_module(f"acquire.migration.{package_name}")
    legacy_module = importlib.import_module(legacy_name)

    assert legacy_module is package_module
    assert package_module.__file__ == str(
        REPOSITORY_ROOT / "src" / "acquire" / "migration" / f"{package_name}.py"
    )


def test_migration_modules_do_not_mutate_sys_path() -> None:
    """Verify packaged migration tools contain no path injection."""
    migration_root = REPOSITORY_ROOT / "src" / "acquire" / "migration"
    for source_path in migration_root.glob("*.py"):
        tree = ast.parse(source_path.read_text())
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "sys"
            and node.func.value.attr == "path"
            for node in ast.walk(tree)
        )


def test_migration_import_creates_no_engine_or_runtime_orm_outside_repository(
    tmp_path: Path,
) -> None:
    """Verify loading installed migration modules has no runtime DB side effect."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import sqlalchemy; calls = []; "
                "sqlalchemy.create_engine = lambda *args, **kwargs: calls.append((args, kwargs)); "
                "from acquire.migration import import_mysql_to_postgres, "
                "validate_import_reports; "
                "assert calls == []; "
                "assert 'acquire.orm' not in sys.modules; "
                "assert validate_import_reports.TABLE_ORDER == "
                "import_mysql_to_postgres.TABLE_ORDER"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module_name", MIGRATION_MODULES)
def test_migration_modules_execute_outside_repository(
    module_name: str,
    tmp_path: Path,
) -> None:
    """Verify installed migration module commands resolve from another cwd."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            f"acquire.migration.{module_name}",
            "--help",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


@pytest.mark.parametrize("command_name", MIGRATION_COMMANDS)
def test_installed_migration_commands_execute_outside_repository(
    command_name: str,
    tmp_path: Path,
) -> None:
    """Verify installed command help has no repository or direct-file dependency."""
    command_path = shutil.which(command_name)
    assert command_path is not None
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [command_path, "--help"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage:")


@pytest.mark.parametrize(("package_name", "legacy_name"), MIGRATION_MODULES.items())
def test_legacy_migration_wrappers_are_minimal_and_owned_by_issue_111(
    package_name: str,
    legacy_name: str,
) -> None:
    """Verify transitional migration files contain only package delegation."""
    wrapper_path = REPOSITORY_ROOT / "server" / f"{legacy_name}.py"
    source = wrapper_path.read_text()
    tree = ast.parse(source)

    assert "issue #111" in source
    assert f"from acquire.migration import {package_name} as _" in source
    assert not any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )
