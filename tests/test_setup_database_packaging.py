"""Verify the packaged database-setup boundary."""

import ast
import importlib
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_packaged_setup_database_is_authoritative_and_legacy_module_is_alias() -> None:
    """Verify both database-setup import paths share one mutable module."""
    package_setup = importlib.import_module("acquire.setup_database")
    legacy_setup = importlib.import_module("setup_database")

    assert legacy_setup is package_setup
    assert package_setup.__file__ == str(
        REPOSITORY_ROOT / "src" / "acquire" / "setup_database.py"
    )


def test_moved_setup_database_does_not_mutate_sys_path() -> None:
    """Verify packaged database setup has no working-directory path injection."""
    source_path = REPOSITORY_ROOT / "src" / "acquire" / "setup_database.py"
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


def test_setup_database_imports_outside_repository_without_pythonpath(
    tmp_path: Path,
) -> None:
    """Verify the editable installed package resolves setup from another directory."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import acquire.setup_database; "
                "assert Path(acquire.setup_database.__file__).name == "
                "'setup_database.py'; "
                "config = acquire.setup_database.alembic_config(); "
                "assert Path(config.config_file_name).name == 'alembic.ini'; "
                "assert Path(config.get_main_option('script_location')).name == "
                "'migrations'"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_setup_database_resources_are_part_of_the_acquire_package() -> None:
    """Verify migration configuration and scripts use package resources."""
    package_root = resources.files("acquire")

    assert package_root.joinpath("alembic.ini").is_file()
    assert package_root.joinpath("migrations", "env.py").is_file()
    assert package_root.joinpath("migrations", "script.py.mako").is_file()
    assert package_root.joinpath(
        "migrations",
        "versions",
        "20260622_0001_baseline_mysql_schema.py",
    ).is_file()


def test_setup_database_command_help_runs_outside_repository_without_database(
    tmp_path: Path,
) -> None:
    """Verify command discovery and help do not initialize a database."""
    command = shutil.which("acquire-setup-database")
    assert command is not None
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("ACQUIRE_DATABASE_URL", None)
    environment["POSTGRES_PORT"] = "private-secret"

    result = subprocess.run(
        [command, "--help"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert "Upgrade the configured Acquire database" in result.stdout
    assert "private-secret" not in result.stdout


def test_setup_database_command_sanitizes_environment_configuration_failure(
    tmp_path: Path,
) -> None:
    """Verify malformed sensitive environment values stay inside the boundary."""
    command = shutil.which("acquire-setup-database")
    assert command is not None
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("ACQUIRE_DATABASE_URL", None)
    environment["POSTGRES_PORT"] = "private-secret"

    result = subprocess.run(
        [command],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "error: database setup failed\n"
    assert "private-secret" not in result.stderr
