"""Verify the packaged replay, stats, and maintenance-tool boundary."""

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
PACKAGE_MODULES = ("log_tools", "recreate_game", "stats")


@pytest.mark.parametrize("package_name", PACKAGE_MODULES)
def test_packaged_offline_tool_is_authoritative(
    package_name: str,
) -> None:
    """Verify each offline tool resolves from the production source layout."""
    package_module = importlib.import_module(f"acquire.{package_name}")

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


def test_stats_roots_default_to_validated_source_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify editable installs retain the repository publication paths."""
    stats = importlib.import_module("acquire.stats")
    monkeypatch.delenv(stats.STATS_DATA_ROOT_ENV, raising=False)
    monkeypatch.delenv(stats.STATS_TEMP_ROOT_ENV, raising=False)

    assert stats.resolve_stats_roots() == (
        REPOSITORY_ROOT / "client" / "stats" / "data",
        REPOSITORY_ROOT / "stats_temp",
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


@pytest.mark.parametrize("root_index", (0, 1))
def test_explicit_stats_roots_must_be_absolute(
    root_index: int,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify explicit command roots cannot restore cwd-dependent behavior."""
    stats = importlib.import_module("acquire.stats")
    roots = [tmp_path / "published", tmp_path / "staging"]
    roots[root_index] = Path("private/relative/root")
    monkeypatch.setenv(stats.STATS_DATA_ROOT_ENV, str(tmp_path / "environment-published"))
    monkeypatch.setenv(stats.STATS_TEMP_ROOT_ENV, str(tmp_path / "environment-staging"))

    with pytest.raises(ValueError, match="must be an absolute path"):
        stats.resolve_stats_roots(*roots)


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


def test_stats_command_help_runs_outside_repository_without_database(
    tmp_path: Path,
) -> None:
    """Verify installed help parses before malformed database configuration."""
    command = shutil.which("acquire-update-stats")
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
    assert "Continuously import logs" in result.stdout
    assert "private-secret" not in result.stdout


def test_stats_module_import_defers_database_and_rating_initialization(
    tmp_path: Path,
) -> None:
    """Verify command parsing does not eagerly load operational dependencies."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("ACQUIRE_DATABASE_URL", None)
    environment["POSTGRES_PORT"] = "private-secret"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import acquire.stats; "
                "assert 'acquire.orm' not in sys.modules; "
                "assert 'trueskill' not in sys.modules"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_stats_command_rejects_relative_roots_without_reflecting_them(
    tmp_path: Path,
) -> None:
    """Verify invalid private paths use the fixed argument diagnostic."""
    command = shutil.which("acquire-update-stats")
    assert command is not None
    private_root = "private/relative/staging"

    result = subprocess.run(
        [command, "--stats-temp-root", private_root],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "error: invalid arguments\n"
    assert private_root not in result.stderr
