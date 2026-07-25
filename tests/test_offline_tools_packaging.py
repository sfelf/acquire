"""Verify the packaged replay, stats, and maintenance-tool boundary."""

import ast
import importlib
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_MODULES = ("log_tools", "recreate_game", "stats")
LEGACY_MODULES = {
    "log_tools": "logs_to_games",
    "recreate_game": "recreate_game",
    "stats": "cron",
}


@pytest.mark.parametrize("package_name", PACKAGE_MODULES)
def test_packaged_offline_tool_is_authoritative_and_legacy_module_is_alias(
    package_name: str,
) -> None:
    """Verify each legacy offline-tool path shares its packaged module object."""
    package_module = importlib.import_module(f"acquire.{package_name}")
    legacy_module = importlib.import_module(LEGACY_MODULES[package_name])

    assert legacy_module is package_module
    assert package_module.__file__ == str(
        REPOSITORY_ROOT / "src" / "acquire" / f"{package_name}.py"
    )


def test_moved_offline_tools_do_not_mutate_sys_path() -> None:
    """Verify packaged tools do not depend on working-directory path injection."""
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


def test_offline_tools_run_outside_repository_without_pythonpath(tmp_path: Path) -> None:
    """Verify installed tools import and execute from an unrelated directory."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    stats_data_root = tmp_path / "published"
    stats_temp_root = tmp_path / "staging"
    environment["ACQUIRE_STATS_DATA_ROOT"] = str(stats_data_root)
    environment["ACQUIRE_STATS_TEMP_ROOT"] = str(stats_temp_root)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from acquire import log_tools, recreate_game, stats; "
                "assert log_tools.get_player_id_to_ranking([90, 70, 70]) "
                "== {0: 1, 1: 2, 2: 2}; "
                "assert stats.decode_database_text(b'alice') == 'alice'; "
                "assert recreate_game.server is log_tools.server; "
                "stats_data_root, stats_temp_root = stats.resolve_stats_roots(); "
                f"assert stats_data_root == Path({str(stats_data_root)!r}); "
                f"assert stats_temp_root == Path({str(stats_temp_root)!r})"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("wrapper_name", "package_name"),
    (
        ("logs_to_games.py", "log_tools"),
        ("recreate_game.py", "recreate_game"),
        ("cron.py", "stats"),
    ),
)
def test_legacy_offline_tool_wrappers_are_minimal_and_owned_by_issue_111(
    wrapper_name: str,
    package_name: str,
) -> None:
    """Verify transitional direct-file paths contain only package delegation."""
    wrapper_path = REPOSITORY_ROOT / "server" / wrapper_name
    source = wrapper_path.read_text()
    tree = ast.parse(source)

    assert "issue #111" in source
    assert f"from acquire import {package_name} as _" in source
    assert not any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )


def test_stats_roots_default_to_validated_source_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify editable installs retain the repository publication paths."""
    stats = importlib.import_module("acquire.stats")
    monkeypatch.delenv(stats.STATS_DATA_ROOT_ENV, raising=False)
    monkeypatch.delenv(stats.STATS_TEMP_ROOT_ENV, raising=False)

    assert stats.resolve_stats_roots() == (
        REPOSITORY_ROOT / "client" / "stats" / "data",
        REPOSITORY_ROOT / "server" / "stats_temp",
    )


def test_stats_roots_require_configuration_outside_source_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify an installed artifact cannot write beneath its package location."""
    stats = importlib.import_module("acquire.stats")
    monkeypatch.delenv(stats.STATS_DATA_ROOT_ENV, raising=False)
    monkeypatch.delenv(stats.STATS_TEMP_ROOT_ENV, raising=False)
    monkeypatch.setattr(stats, "SOURCE_PROJECT_ROOT", tmp_path / "site-packages")

    with pytest.raises(RuntimeError, match=stats.STATS_DATA_ROOT_ENV):
        stats.resolve_stats_roots()


@pytest.mark.parametrize("environment_name", ("STATS_DATA_ROOT_ENV", "STATS_TEMP_ROOT_ENV"))
def test_stats_roots_reject_relative_environment_configuration(
    environment_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify configured installed roots do not reintroduce cwd dependence."""
    stats = importlib.import_module("acquire.stats")
    variable_name = getattr(stats, environment_name)
    monkeypatch.setenv(variable_name, "relative/path")

    with pytest.raises(ValueError, match=f"{variable_name} must be an absolute path"):
        stats.resolve_stats_roots()


def test_explicit_stats_roots_override_environment_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify embedding callers can provide both roots directly."""
    stats = importlib.import_module("acquire.stats")
    monkeypatch.setenv(stats.STATS_DATA_ROOT_ENV, "invalid-relative-path")
    monkeypatch.setenv(stats.STATS_TEMP_ROOT_ENV, "invalid-relative-path")
    stats_data_root = tmp_path / "published"
    stats_temp_root = tmp_path / "staging"

    assert stats.resolve_stats_roots(stats_data_root, stats_temp_root) == (
        stats_data_root,
        stats_temp_root,
    )


def test_stats_roots_use_absolute_environment_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify installed artifacts resolve both configured roots."""
    stats = importlib.import_module("acquire.stats")
    stats_data_root = tmp_path / "published"
    stats_temp_root = tmp_path / "staging"
    monkeypatch.setenv(stats.STATS_DATA_ROOT_ENV, str(stats_data_root))
    monkeypatch.setenv(stats.STATS_TEMP_ROOT_ENV, str(stats_temp_root))

    assert stats.resolve_stats_roots() == (stats_data_root, stats_temp_root)


@pytest.mark.parametrize(
    ("wrapper_name", "package_name"),
    (
        ("logs_to_games.py", "log_tools"),
        ("cron.py", "stats"),
    ),
)
def test_direct_file_entry_points_delegate_to_packaged_main(
    wrapper_name: str,
    package_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify existing script paths invoke the authoritative package command."""
    package_module = importlib.import_module(f"acquire.{package_name}")
    calls: list[str] = []
    monkeypatch.setattr(package_module, "main", lambda: calls.append(package_name))

    runpy.run_path(
        str(REPOSITORY_ROOT / "server" / wrapper_name),
        run_name="__main__",
    )

    assert calls == [package_name]
