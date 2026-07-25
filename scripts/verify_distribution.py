"""Verify final Acquire release artifacts from a repository checkout.

This fail-closed release boundary derives exact manifests from tracked source,
builds the sdist and direct wheel, safely extracts the sdist to rebuild its
wheel, and independently exercises both wheels in clean environments outside
the checkout. Verification coordinates Git inventory, package installation,
subprocess and loopback-network checks, optional fresh-database mutation, and
the MySQL-extra boundary. It requires Git, uv, index access for declared
dependencies, loopback sockets, and optionally disposable Postgres; any
missing, partial, failed, or unknown result terminates the workflow.
"""

from __future__ import annotations

import os
import shutil
import socket
import stat
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


class VerificationError(RuntimeError):
    """Raised when an artifact or installed boundary violates its contract."""


def require(condition: bool, message: str) -> None:
    """Fail verification explicitly when a required condition is false.

    This helper intentionally avoids Python assertions so optimization cannot
    disable release checks or skip expressions with verification side effects.

    Args:
        condition: Whether the required release condition holds.
        message: Fixed diagnostic describing the violated contract.

    Raises:
        VerificationError: The condition is false.
    """
    if not condition:
        raise VerificationError(message)


def run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a verification command and require success.

    The child inherits normal output unless capture is requested. A nonzero
    status aborts the verifier immediately rather than allowing later checks to
    treat partial build or installation output as valid.

    Args:
        command: Command and arguments to execute.
        cwd: Working directory for the child process.
        environment: Optional complete child environment.
        capture_output: Whether to retain stdout and stderr.

    Returns:
        Completed successful child process.

    Raises:
        subprocess.CalledProcessError: The child command returns nonzero.
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

    Every member name must be unique and either name the exact
    `acquire-0.1.0` root directory or live below its `acquire-0.1.0/` prefix.
    Directories and regular files are the only accepted member types; links and
    other special members fail before regular-file names are normalized into
    the expected manifest.

    Args:
        path: Source-distribution archive.

    Returns:
        File paths relative to the versioned archive root.

    Raises:
        VerificationError: Member names are duplicated, a member is outside
            the versioned root, or a member has an unsupported type.
    """
    prefix = f"{SDIST_ROOT}/"
    with tarfile.open(path, "r:gz") as archive:
        archive_members = archive.getmembers()
    member_names = unique_archive_names(
        [member.name for member in archive_members],
        "source distribution",
    )
    require(
        all(name == SDIST_ROOT or name.startswith(prefix) for name in member_names),
        "source distribution contains a member outside its versioned root",
    )
    require(
        all(member.isfile() or member.isdir() for member in archive_members),
        "source distribution contains an unsupported member type",
    )
    return {
        member.name.removeprefix(prefix)
        for member in archive_members
        if member.isfile()
    }


def wheel_manifest(path: Path) -> set[str]:
    """Read unique regular-file names from a wheel.

    Duplicate names are rejected before directory entries are omitted so an
    installer cannot choose ambiguously between repeated members. Entries with
    a declared Unix type must be regular files or directories; links and other
    special members fail verification.

    Args:
        path: Wheel archive.

    Returns:
        Complete wheel file manifest.

    Raises:
        VerificationError: Member names are duplicated or a member has an
            unsupported type.
    """
    with zipfile.ZipFile(path) as archive:
        archive_members = archive.infolist()
    unique_archive_names(
        [member.filename for member in archive_members],
        "wheel",
    )
    require(
        all(wheel_member_type_is_supported(member) for member in archive_members),
        "wheel contains an unsupported member type",
    )
    return {member.filename for member in archive_members if not member.is_dir()}


def unique_archive_names(names: list[str], artifact: str) -> set[str]:
    """Require archive member names to be unique.

    Duplicate names make installation ambiguous even when the deduplicated
    inventory matches policy, so validation occurs before callers classify or
    normalize members.

    Args:
        names: Archive member names in stored order.
        artifact: Fixed artifact label for the failure diagnostic.

    Returns:
        Unique member names.

    Raises:
        VerificationError: Any member name occurs more than once.
    """
    unique_names = set(names)
    require(
        len(unique_names) == len(names),
        f"{artifact} contains duplicate member names",
    )
    return unique_names


def wheel_member_type_is_supported(member: zipfile.ZipInfo) -> bool:
    """Return whether a wheel member is a regular file or directory.

    Zip entries may omit a Unix file type, which is accepted for portability.
    When a type is declared, it must agree with the entry's directory marker;
    symbolic links and other special filesystem objects are rejected.

    Args:
        member: Wheel member metadata.

    Returns:
        Whether the member type is supported.
    """
    member_type = stat.S_IFMT(member.external_attr >> 16)
    if member.is_dir():
        return member_type in {0, stat.S_IFDIR}
    return member_type in {0, stat.S_IFREG}


def verify_manifest(actual: set[str], expected: set[str], artifact: str) -> None:
    """Require an artifact manifest to match its complete policy inventory.

    Args:
        actual: File names present in the built artifact.
        expected: Complete expected file names.
        artifact: Human-readable artifact kind for failures.

    Raises:
        VerificationError: Required files are missing or unexpected files
            exist.
    """
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    require(
        not missing and not unexpected,
        f"{artifact} manifest mismatch; missing={missing!r}; unexpected={unexpected!r}",
    )


def build_artifacts(output: Path) -> tuple[Path, Path]:
    """Build the repository source distribution and wheel.

    The output directory is mutated by `uv build`. Both returned paths must be
    treated as provisional until their complete manifests and clean-installed
    behavior pass later verification.

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

    This creates dedicated unpack and rebuild directories below `workspace`,
    safely extracts the sdist, and invokes the backend against only that
    extracted tree. Existing paths with those names are not accepted.

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
    """Return a sanitized environment for installed-artifact checks.

    The child inherits the host environment except for `PYTHONPATH`, which
    could import repository code instead of the installed wheel;
    `ACQUIRE_ARTIFACT_POSTGRES_URL` and `ACQUIRE_DATABASE_URL`, which could
    select ambient or verifier-owned databases; and `ACQUIRE_STATS_DATA_ROOT`
    plus `ACQUIRE_STATS_TEMP_ROOT`, which could redirect filesystem behavior.
    Individual checks add back only the database setting they explicitly own.

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

    The command must exit successfully and write nothing to stderr. This check
    intentionally runs from an external working directory with repository
    import overrides removed.

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
    require(result.stderr == "", f"{command.name} wrote unexpected help stderr")


def verify_editable_commands(workspace: Path) -> None:
    """Smoke-test all project scripts from the editable development install.

    Every declared command must resolve on the active `uv run` path and its
    help boundary must work from the external workspace. Missing commands,
    nonzero exits, or unexpected stderr abort verification.

    Args:
        workspace: External working directory.
    """
    environment = clean_environment()
    for command in COMMANDS:
        resolved = shutil.which(command)
        if resolved is None:
            raise VerificationError(f"editable command is unavailable: {command}")
        smoke_command_help(Path(resolved), workspace, environment)


def reserve_port() -> int:
    """Return an available loopback TCP port.

    The probing socket is closed before return so the installed gateway can
    bind the port. A concurrent process can claim it in that interval; the
    gateway lifecycle check will then fail rather than retrying another port.

    Returns:
        Ephemeral port number released for the gateway smoke test.

    Raises:
        OSError: A loopback socket cannot be bound.
    """
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def fetch_until_ready(url: str, process: subprocess.Popen[str]) -> bytes:
    """Fetch an asset after the installed gateway starts.

    Poll for at most 15 seconds, using one-second request timeouts and
    100-millisecond retry intervals. An early child exit fails immediately;
    otherwise failure to receive a response before the deadline is a readiness
    timeout. Both terminal states raise `VerificationError`.

    Args:
        url: Asset URL to request.
        process: Gateway child process.

    Returns:
        Response body.

    Raises:
        VerificationError: The child exits early or readiness times out.
    """
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise VerificationError(
                f"installed gateway exited with {process.returncode}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                body = response.read()
                if not isinstance(body, bytes):
                    raise VerificationError("installed gateway response type is invalid")
                return body
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise VerificationError("installed gateway did not become ready")


def verify_installed_gateway(
    command: Path,
    workspace: Path,
    environment: dict[str, str],
) -> None:
    """Verify external assets and invalid-root diagnostics from the clean wheel.

    This creates representative main and stats trees, starts the installed
    gateway on loopback, polls and validates both asset responses, and always
    terminates the child. Graceful termination has a ten-second deadline before
    forced cleanup. After shutdown, separate invocations verify the exact
    missing-root and relative-root failure contracts.

    Args:
        command: Clean-installed HTTP gateway command.
        workspace: External temporary workspace.
        environment: Sanitized child environment.

    Raises:
        VerificationError: Asset serving or a fixed diagnostic differs from
            the installed gateway contract.
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
        main_body = fetch_until_ready(f"http://127.0.0.1:{port}/", process)
        require(
            main_body == b"clean-wheel-main\n",
            "installed gateway returned the wrong main asset",
        )
        stats_body = fetch_until_ready(f"http://127.0.0.1:{port}/stats/", process)
        require(
            stats_body == b"clean-wheel-stats\n",
            "installed gateway returned the wrong stats asset",
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
    require(missing.returncode == 1, "missing static roots returned the wrong status")
    require(missing.stdout == "", "missing static roots wrote unexpected stdout")
    require(
        missing.stderr == "error: HTTP server configuration failed\n",
        "missing static roots returned the wrong diagnostic",
    )

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
    require(invalid.returncode == 2, "relative static roots returned the wrong status")
    require(invalid.stdout == "", "relative static roots wrote unexpected stdout")
    require(
        invalid.stderr == "error: invalid arguments\n",
        "relative static roots returned the wrong diagnostic",
    )


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
    """Install and exercise one wheel outside the repository.

    Ordering is significant: create a fresh virtual environment, install the
    wheel with normal dependencies, prove MySQL is absent, inspect metadata and
    packaged Alembic resources, exercise all commands and external gateway
    assets, and validate explicit stats roots. When a Postgres URL is supplied,
    database setup runs twice before the environment is mutated by installing
    the `mysql-migration` extra. The final checks prove that extra activates
    both the connector and importer command.

    Args:
        wheel: Direct or source-distribution-rebuilt wheel to verify.
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
        "import importlib.metadata, importlib.util\n"
        "from importlib import resources\n"
        "from pathlib import Path\n"
        "import acquire\n"
        "root = resources.files('acquire')\n"
        "if 'site-packages' not in Path(acquire.__file__).parts:\n"
        "    raise RuntimeError('acquire did not import from site-packages')\n"
        "if not root.joinpath('alembic.ini').is_file():\n"
        "    raise RuntimeError('installed alembic.ini is unavailable')\n"
        "if not root.joinpath('migrations', 'env.py').is_file():\n"
        "    raise RuntimeError('installed migration environment is unavailable')\n"
        "if not root.joinpath('migrations', 'script.py.mako').is_file():\n"
        "    raise RuntimeError('installed migration template is unavailable')\n"
        "if not root.joinpath('migrations', 'versions', "
        "'20260622_0001_baseline_mysql_schema.py').is_file():\n"
        "    raise RuntimeError('installed baseline revision is unavailable')\n"
        "if importlib.util.find_spec('mysql') is not None:\n"
        "    raise RuntimeError('normal wheel unexpectedly installed MySQL')\n"
        f"if set(importlib.metadata.distribution('acquire').entry_points.names) "
        f"!= {set(COMMANDS)!r}:\n"
        "    raise RuntimeError('installed entry points differ from policy')\n"
    )
    run([str(python), "-c", inspection], cwd=workspace, environment=environment)

    installed_commands = {
        command: command_path(environment_root, command) for command in COMMANDS
    }
    for command in installed_commands.values():
        require(command.is_file(), f"installed command is unavailable: {command.name}")
        smoke_command_help(command, workspace, environment)

    verify_installed_gateway(
        installed_commands["acquire-http-server"],
        workspace,
        environment,
    )

    data_root = workspace / "published"
    temp_root = workspace / "staging"
    stats_check = (
        "from pathlib import Path\n"
        "from acquire.stats import resolve_stats_roots\n"
        f"data = Path({str(data_root)!r})\n"
        f"temp = Path({str(temp_root)!r})\n"
        "if resolve_stats_roots(data, temp) != (data, temp):\n"
        "    raise RuntimeError('installed stats roots differ from explicit roots')\n"
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
    require(importer.returncode == 2, "invalid importer URLs returned the wrong status")
    require(importer.stdout == "", "invalid importer URLs wrote unexpected stdout")
    require(
        importer.stderr == "error: invalid database connection arguments\n",
        "invalid importer URLs returned the wrong diagnostic",
    )


def main() -> None:
    """Build, inspect, rebuild, install, and exercise final artifacts.

    The workflow uses one disposable external root. It verifies exact sdist and
    wheel manifests before installation, exercises the editable command
    surface, then independently clean-installs both the direct wheel and the
    wheel rebuilt from the unpacked sdist. Optional Postgres mutation is
    reserved for the rebuilt-wheel path required by the artifact contract.
    Any incomplete or unknown state aborts the workflow.
    """
    postgres_url = os.environ.get("ACQUIRE_ARTIFACT_POSTGRES_URL")
    with tempfile.TemporaryDirectory(prefix="acquire-artifacts-") as temporary:
        workspace = Path(temporary)
        artifacts = workspace / "artifacts"
        artifacts.mkdir()
        sdist, direct_wheel = build_artifacts(artifacts)
        expected_source = expected_sdist_manifest()
        expected_wheel = expected_wheel_manifest()
        verify_manifest(sdist_manifest(sdist), expected_source, "source distribution")
        verify_manifest(wheel_manifest(direct_wheel), expected_wheel, "direct wheel")
        rebuilt_wheel = build_wheel_from_sdist(sdist, workspace)
        verify_manifest(wheel_manifest(rebuilt_wheel), expected_wheel, "rebuilt wheel")
        verify_editable_commands(workspace)
        direct_workspace = workspace / "direct-wheel-install"
        direct_workspace.mkdir()
        verify_clean_wheel(direct_wheel, direct_workspace, None)
        rebuilt_workspace = workspace / "rebuilt-wheel-install"
        rebuilt_workspace.mkdir()
        verify_clean_wheel(rebuilt_wheel, rebuilt_workspace, postgres_url)


if __name__ == "__main__":
    main()
