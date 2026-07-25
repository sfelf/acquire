"""Verify the packaged ORM and Alembic migration boundary."""

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_packaged_orm_is_authoritative_and_legacy_module_is_alias() -> None:
    """Verify both import paths share one mutable ORM module."""
    package_orm = importlib.import_module("acquire.orm")
    legacy_orm = importlib.import_module("orm")

    assert legacy_orm is package_orm
    assert package_orm.__file__ == str(REPOSITORY_ROOT / "src" / "acquire" / "orm.py")


def test_moved_orm_and_alembic_environment_do_not_mutate_sys_path() -> None:
    """Verify the migrated persistence boundary has no server-path injection."""
    for path in (
        REPOSITORY_ROOT / "src" / "acquire" / "orm.py",
        REPOSITORY_ROOT / "src" / "acquire" / "migrations" / "env.py",
    ):
        tree = ast.parse(path.read_text())
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "sys"
            and node.func.value.attr == "path"
            for node in ast.walk(tree)
        )


def test_alembic_offline_upgrade_loads_packaged_metadata_outside_repository(
    tmp_path: Path,
) -> None:
    """Verify Alembic resolves its scripts and ORM from an unrelated directory."""
    environment = os.environ.copy()
    environment["ACQUIRE_DATABASE_URL"] = "postgresql+psycopg://user:pass@localhost/acquire"
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(REPOSITORY_ROOT / "alembic.ini"),
            "upgrade",
            "head",
            "--sql",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE game" in result.stdout
