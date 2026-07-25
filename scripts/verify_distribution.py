"""Verify Acquire distribution manifests and clean installed commands."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "acquire"
PROJECT_VERSION = "0.1.0"
SDIST_ROOT = f"{PROJECT_NAME}-{PROJECT_VERSION}"
DIST_INFO_ROOT = f"{PROJECT_NAME}-{PROJECT_VERSION}.dist-info"
COMMANDS = (
    "acquire-generate-enums",
    "acquire-http-server",
    "acquire-migrate-mysql-to-postgres",
    "acquire-setup-database",
    "acquire-update-stats",
    "acquire-validate-migration-reports",
)


def run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a verification command and require success.

    Args:
        command: Command and arguments to execute.
        cwd: Working directory for the child process.
        environment: Optional complete child environment.
        capture_output: Whether to retain stdout and stderr.

    Returns:
        Completed successful child process.
    """
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=capture_output,
        text=True,
    )


def tracked_files(*patterns: str) -> set[str]:
    """Return tracked repository files matching Git pathspecs.

    Args:
        patterns: Git pathspecs selecting the artifact-owned source inventory.

    Returns:
        Repository-relative tracked file names.
    """
    result = run(
        ["git", "ls-files", "--", *patterns],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
    )
    return set(result.stdout.splitlines())


def expected_sdist_manifest() -> set[str]:
    """Return the complete expected source-distribution file manifest.

    Returns:
        Paths relative to the source-distribution root.
    """
    return {
        "PKG-INFO",
        "README.md",
        "pyproject.toml",
        *tracked_files("src/acquire/**", "tests/**"),
    }


def expected_wheel_manifest() -> set[str]:
    """Return the complete expected wheel file manifest.

    Returns:
        Wheel member paths including package and metadata files.
    """
    package_files = {
        path.removeprefix("src/") for path in tracked_files("src/acquire/**")
    }
    return package_files | {
        f"{DIST_INFO_ROOT}/METADATA",
        f"{DIST_INFO_ROOT}/RECORD",
        f"{DIST_INFO_ROOT}/WHEEL",
        f"{DIST_INFO_ROOT}/entry_points.txt",
    }


def sdist_manifest(path: Path) -> set[str]:
    """Read normalized file names from a gzipped source distribution.

    Args:
        path: Source-distribution archive.

    Returns:
        File paths relative to the versioned archive root.
    """
    prefix = f"{SDIST_ROOT}/"
    with tarfile.open(path, "r:gz") as archive:
        members = {member.name for member in archive.getmembers() if member.isfile()}
    assert all(member.startswith(prefix) for member in members), members
    return {member.removeprefix(prefix) for member in members}


def wheel_manifest(path: Path) -> set[str]:
    """Read file names from a wheel.

    Args:
        path: Wheel archive.

    Returns:
        Complete wheel file manifest.
    """
    with zipfile.ZipFile(path) as archive:
        return {name for name in archive.namelist() if not name.endswith("/")}


def assert_manifest(actual: set[str], expected: set[str], artifact: str) -> None:
    """Require an artifact manifest to match its complete policy inventory.

    Args:
        actual: File names present in the built artifact.
        expected: Complete expected file names.
        artifact: Human-readable artifact kind for failures.
    """
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    assert not missing and not unexpected, (
        f"{artifact} manifest mismatch; missing={missing!r}; unexpected={unexpected!r}"
    )


def build_artifacts(output: Path) -> tuple[Path, Path]:
    """Build the repository source distribution and wheel.

    Args:
        output: Empty external directory for build outputs.

    Returns:
        Source-distribution and direct-wheel paths.
    """
    run(
        ["uv", "build", "--no-sources", "--out-dir", str(output)],
        cwd=REPOSITORY_ROOT,
    )
    return (
        output / f"{PROJECT_NAME}-{PROJECT_VERSION}.tar.gz",
        output / f"{PROJECT_NAME}-{PROJECT_VERSION}-py3-none-any.whl",
    )


def build_wheel_from_sdist(sdist: Path, workspace: Path) -> Path:
    """Build a wheel from an unpacked source distribution.

    Args:
        sdist: Verified source-distribution archive.
        workspace: External temporary workspace.

    Returns:
        Wheel built from the unpacked source distribution.
    """
    unpacked = workspace / "unpacked"
    unpacked.mkdir()
    with tarfile.open(sdist, "r:gz") as archive:
        archive.extractall(unpacked, filter="data")
    source_root = unpacked / SDIST_ROOT
    output = workspace / "rebuilt"
    output.mkdir()
    run(
        [
            "uv",
            "build",
            "--wheel",
            "--no-sources",
            "--out-dir",
            str(output),
            str(source_root),
        ],
        cwd=workspace,
    )
    return output / f"{PROJECT_NAME}-{PROJECT_VERSION}-py3-none-any.whl"


def clean_environment() -> dict[str, str]:
    """Return an environment without repository import overrides.

    Returns:
        Sanitized child-process environment.
    """
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("ACQUIRE_ARTIFACT_POSTGRES_URL", None)
    environment.pop("ACQUIRE_DATABASE_URL", None)
    environment.pop("ACQUIRE_STATS_DATA_ROOT", None)
    environment.pop("ACQUIRE_STATS_TEMP_ROOT", None)
    return environment


def command_path(environment_root: Path, command: str) -> Path:
    """Return an installed command path for the current platform.

    Args:
        environment_root: Virtual-environment root.
        command: Project script name.

    Returns:
        Absolute installed command path.
    """
    scripts = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return environment_root / scripts / f"{command}{suffix}"


def smoke_command_help(command: Path, cwd: Path, environment: dict[str, str]) -> None:
    """Require an installed command's help boundary to resolve.

    Args:
        command: Installed project script.
        cwd: External working directory.
        environment: Sanitized child environment.
    """
    result = run(
        [str(command), "--help"],
        cwd=cwd,
        environment=environment,
        capture_output=True,
    )
    assert result.stderr == "", (command.name, result.stderr)


def verify_editable_commands(workspace: Path) -> None:
    """Smoke-test all project scripts from the editable development install.

    Args:
        workspace: External working directory.
    """
    environment = clean_environment()
    for command in COMMANDS:
        resolved = shutil.which(command)
        assert resolved is not None, command
        smoke_command_help(Path(resolved), workspace, environment)


def reserve_port() -> int:
    """Return an available loopback TCP port.

    Returns:
        Ephemeral port number released for the gateway smoke test.
    """
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def fetch_until_ready(url: str, process: subprocess.Popen[str]) -> bytes:
    """Fetch an asset after the installed gateway starts.

    Args:
        url: Asset URL to request.
        process: Gateway child process.

    Returns:
        Response body.
    """
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"installed gateway exited with {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                body = response.read()
                assert isinstance(body, bytes)
                return body
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise AssertionError("installed gateway did not become ready")


def verify_installed_gateway(
    command: Path,
    workspace: Path,
    environment: dict[str, str],
) -> None:
    """Verify external assets and invalid-root diagnostics from the clean wheel.

    Args:
        command: Clean-installed HTTP gateway command.
        workspace: External temporary workspace.
        environment: Sanitized child environment.
    """
    main_root = workspace / "main-assets"
    stats_root = workspace / "stats-assets"
    main_root.mkdir()
    stats_root.mkdir()
    (main_root / "index.html").write_text("clean-wheel-main\n")
    (stats_root / "index.html").write_text("clean-wheel-stats\n")
    port = reserve_port()
    process = subprocess.Popen(
        [
            str(command),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--main-static-root",
            str(main_root),
            "--stats-static-root",
            str(stats_root),
        ],
        cwd=workspace,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert fetch_until_ready(f"http://127.0.0.1:{port}/", process) == (
            b"clean-wheel-main\n"
        )
        assert fetch_until_ready(f"http://127.0.0.1:{port}/stats/", process) == (
            b"clean-wheel-stats\n"
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    missing = run_failure(
        [
            str(command),
            "--main-static-root",
            str(workspace / "missing-main"),
            "--stats-static-root",
            str(workspace / "missing-stats"),
        ],
        cwd=workspace,
        environment=environment,
    )
    assert missing.returncode == 1
    assert missing.stdout == ""
    assert missing.stderr == "error: HTTP server configuration failed\n"

    invalid = run_failure(
        [
            str(command),
            "--main-static-root",
            "relative-main",
            "--stats-static-root",
            "relative-stats",
        ],
        cwd=workspace,
        environment=environment,
    )
    assert invalid.returncode == 2
    assert invalid.stdout == ""
    assert invalid.stderr == "error: invalid arguments\n"


def run_failure(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run a command expected to return a nonzero status.

    Args:
        command: Command and arguments.
        cwd: External working directory.
        environment: Sanitized child environment.

    Returns:
        Completed child process without enforcing its status.
    """
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def verify_clean_wheel(
    wheel: Path,
    workspace: Path,
    postgres_url: str | None,
) -> None:
    """Install and exercise a rebuilt wheel outside the repository.

    Args:
        wheel: Wheel rebuilt from the unpacked source distribution.
        workspace: External temporary workspace.
        postgres_url: Optional fresh Postgres database used for setup verification.
    """
    environment_root = workspace / "clean-environment"
    run(
        ["uv", "venv", "--python", sys.executable, str(environment_root)],
        cwd=workspace,
    )
    python = command_path(environment_root, "python")
    run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        cwd=workspace,
    )
    environment = clean_environment()
    inspection = (
        "import importlib.metadata, importlib.util; "
        "from importlib import resources; "
        "from pathlib import Path; "
        "import acquire; "
        "root = resources.files('acquire'); "
        "assert 'site-packages' in Path(acquire.__file__).parts; "
        "assert root.joinpath('alembic.ini').is_file(); "
        "assert root.joinpath('migrations', 'env.py').is_file(); "
        "assert root.joinpath('migrations', 'script.py.mako').is_file(); "
        "assert root.joinpath('migrations', 'versions', "
        "'20260622_0001_baseline_mysql_schema.py').is_file(); "
        "assert importlib.util.find_spec('mysql') is None; "
        f"assert set(importlib.metadata.distribution('acquire').entry_points.names) "
        f"== {set(COMMANDS)!r}"
    )
    run([str(python), "-c", inspection], cwd=workspace, environment=environment)

    installed_commands = {
        command: command_path(environment_root, command) for command in COMMANDS
    }
    for command in installed_commands.values():
        assert command.is_file(), command
        smoke_command_help(command, workspace, environment)

    verify_installed_gateway(
        installed_commands["acquire-http-server"],
        workspace,
        environment,
    )

    data_root = workspace / "published"
    temp_root = workspace / "staging"
    stats_check = (
        "from pathlib import Path; "
        "from acquire.stats import resolve_stats_roots; "
        f"data = Path({str(data_root)!r}); temp = Path({str(temp_root)!r}); "
        "assert resolve_stats_roots(data, temp) == (data, temp)"
    )
    run([str(python), "-c", stats_check], cwd=workspace, environment=environment)

    if postgres_url is not None:
        setup_environment = environment.copy()
        setup_environment["ACQUIRE_DATABASE_URL"] = postgres_url
        for _ in range(2):
            run(
                [str(installed_commands["acquire-setup-database"])],
                cwd=workspace,
                environment=setup_environment,
            )

    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            f"{wheel}[mysql-migration]",
        ],
        cwd=workspace,
    )
    run(
        [
            str(python),
            "-c",
            "import mysql.connector; "
            "import acquire.migration.import_mysql_to_postgres",
        ],
        cwd=workspace,
        environment=environment,
    )
    importer = run_failure(
        [
            str(installed_commands["acquire-migrate-mysql-to-postgres"]),
            "--source-url",
            "",
            "--target-url",
            "",
        ],
        cwd=workspace,
        environment=environment,
    )
    assert importer.returncode == 2
    assert importer.stdout == ""
    assert importer.stderr == "error: invalid database connection arguments\n"


def main() -> None:
    """Build, inspect, rebuild, install, and exercise final artifacts."""
    postgres_url = os.environ.get("ACQUIRE_ARTIFACT_POSTGRES_URL")
    with tempfile.TemporaryDirectory(prefix="acquire-artifacts-") as temporary:
        workspace = Path(temporary)
        artifacts = workspace / "artifacts"
        artifacts.mkdir()
        sdist, direct_wheel = build_artifacts(artifacts)
        expected_source = expected_sdist_manifest()
        expected_wheel = expected_wheel_manifest()
        assert_manifest(sdist_manifest(sdist), expected_source, "source distribution")
        assert_manifest(wheel_manifest(direct_wheel), expected_wheel, "direct wheel")
        rebuilt_wheel = build_wheel_from_sdist(sdist, workspace)
        assert_manifest(wheel_manifest(rebuilt_wheel), expected_wheel, "rebuilt wheel")
        verify_editable_commands(workspace)
        verify_clean_wheel(rebuilt_wheel, workspace, postgres_url)


if __name__ == "__main__":
    main()
