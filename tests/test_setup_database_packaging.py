"""Verify the packaged database-setup boundary."""

import ast
import importlib
import os
import subprocess
import sys
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
                "assert acquire.setup_database.REPO_DIR == Path("
                f"{str(REPOSITORY_ROOT)!r})"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
