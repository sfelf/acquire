"""Verify the packaged game and realtime HTTP runtime boundary."""

import ast
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_MODULES = ("game_server", "realtime", "http_server")


@pytest.mark.parametrize("package_name", PACKAGE_MODULES)
def test_packaged_runtime_is_authoritative(
    package_name: str,
) -> None:
    """Verify each runtime module resolves from the production source layout."""
    package_module = importlib.import_module(f"acquire.{package_name}")

    assert package_module.__file__ == str(
        REPOSITORY_ROOT / "src" / "acquire" / f"{package_name}.py"
    )


def test_moved_runtime_modules_do_not_mutate_sys_path() -> None:
    """Verify packaged runtime imports do not depend on path injection."""
    for module_name in PACKAGE_MODULES:
        source_path = REPOSITORY_ROOT / "src" / "acquire" / f"{module_name}.py"
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


def test_runtime_imports_outside_repository_without_pythonpath(tmp_path: Path) -> None:
    """Verify installed runtime imports resolve from an unrelated directory."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from acquire import game_server, http_server, realtime; "
                "assert realtime.game_server_module is game_server; "
                "assert http_server.realtime is realtime; "
                f"assert http_server.DEFAULT_MAIN_STATIC_ROOT == "
                f"Path({str(REPOSITORY_ROOT / 'client' / 'main')!r}); "
                f"assert http_server.DEFAULT_STATS_STATIC_ROOT == "
                f"Path({str(REPOSITORY_ROOT / 'client' / 'stats')!r})"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_installed_http_server_command_runs_outside_repository(
    tmp_path: Path,
) -> None:
    """Verify installed help and configuration failure need no source cwd."""
    command = shutil.which("acquire-http-server")
    assert command is not None
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    missing_root = tmp_path / "private-missing-root"

    help_result = subprocess.run(
        [command, "--help"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    failure_result = subprocess.run(
        [
            command,
            "--main-static-root",
            str(missing_root),
            "--stats-static-root",
            str(missing_root),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert help_result.returncode == 0
    assert help_result.stderr == ""
    assert "Serve Acquire HTTP routes from Python" in help_result.stdout
    assert failure_result.returncode == 1
    assert failure_result.stdout == ""
    assert failure_result.stderr == "error: HTTP server configuration failed\n"
    assert str(missing_root) not in failure_result.stderr


def test_runtime_static_roots_match_editable_and_container_layouts() -> None:
    """Verify module-relative asset roots cover both supported source layouts."""
    editable_module = REPOSITORY_ROOT / "src" / "acquire" / "http_server.py"
    container_module = Path("/app/src/acquire/http_server.py")

    assert editable_module.parents[2] / "client" == REPOSITORY_ROOT / "client"
    assert container_module.parents[2] / "client" == Path("/app/client")
