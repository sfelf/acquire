"""Verify the packaged authentication boundary."""

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_packaged_auth_is_authoritative_and_legacy_module_is_alias() -> None:
    """Verify both auth import paths share one mutable module."""
    package_auth = importlib.import_module("acquire.auth")
    legacy_auth = importlib.import_module("auth")

    assert legacy_auth is package_auth
    assert package_auth.__file__ == str(REPOSITORY_ROOT / "src" / "acquire" / "auth.py")


def test_moved_auth_does_not_mutate_sys_path() -> None:
    """Verify packaged authentication has no working-directory path injection."""
    source_path = REPOSITORY_ROOT / "src" / "acquire" / "auth.py"
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


def test_auth_imports_outside_repository_without_pythonpath(tmp_path: Path) -> None:
    """Verify the editable installed package resolves auth from another directory."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import acquire.auth; "
                "assert Path(acquire.auth.__file__).name == 'auth.py'"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
