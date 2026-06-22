import importlib
import os
import socket
import subprocess
import sys
import time
import types
from pathlib import Path
from urllib.parse import quote

import pytest
import sqlalchemy

REPO_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _is_marker_selected(config, marker):
    markexpr = config.option.markexpr
    return bool(markexpr and marker in markexpr)


def _docker_compose_command(project_name, include_test_override=False):
    command = [
        "docker",
        "compose",
        "-p",
        project_name,
        "-f",
        "docker-compose.yml",
    ]
    if include_test_override:
        command.extend(["-f", "docker-compose.test.yml"])
    return command


def _run_docker_compose(project_name, *args, include_test_override=False):
    return subprocess.run(
        [
            *_docker_compose_command(project_name, include_test_override=include_test_override),
            *args,
        ],
        check=True,
        cwd=REPO_DIR,
        text=True,
    )


def _cleanup_docker_compose(project_name, *args, include_test_override=False):
    subprocess.run(
        [
            *_docker_compose_command(project_name, include_test_override=include_test_override),
            *args,
        ],
        check=False,
        cwd=REPO_DIR,
        text=True,
    )


def _get_available_local_port():
    """Return an available loopback port for disposable Docker marker services.

    Some restricted local environments permit Docker but block direct socket
    binding from the pytest process. In that case, use the documented Postgres
    test override port and let Docker report any real bind conflict.

    Returns:
        Available local port, or the documented Postgres test port fallback.
    """
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", 0))
        except OSError:
            return "35432"
        return str(sock.getsockname()[1])


@pytest.fixture(scope="session")
def mysql_test_url(pytestconfig):
    configured_url = os.environ.get("ACQUIRE_MYSQL_TEST_URL")
    if configured_url:
        yield configured_url
        return
    if not _is_marker_selected(pytestconfig, "mysql"):
        pytest.skip("mysql marker was not selected")

    project_name = f"acquire-pytest-mysql-{os.getpid()}"
    mysql_port = os.environ.get("ACQUIRE_MYSQL_TEST_PORT", "33061")
    compose_env = {
        "ACQUIRE_MYSQL_TEST_PORT": mysql_port,
        "MYSQL_DATABASE": os.environ.get("MYSQL_DATABASE", "acquire"),
        "MYSQL_USER": os.environ.get("MYSQL_USER", "acquire"),
        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "acquire"),
    }
    previous_env = {key: os.environ.get(key) for key in compose_env}
    os.environ.update(compose_env)
    try:
        _run_docker_compose(project_name, "up", "-d", "mysql", include_test_override=True)
        yield (
            "mysql+mysqlconnector://{}:{}@127.0.0.1:{}/{}".format(
                quote(compose_env["MYSQL_USER"], safe=""),
                quote(compose_env["MYSQL_PASSWORD"], safe=""),
                mysql_port,
                compose_env["MYSQL_DATABASE"],
            )
        )
    finally:
        _cleanup_docker_compose(project_name, "down", "--volumes", include_test_override=True)
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session")
def postgres_test_url(pytestconfig):
    configured_url = os.environ.get("ACQUIRE_POSTGRES_TEST_URL")
    if configured_url:
        yield configured_url
        return
    if not _is_marker_selected(pytestconfig, "postgres"):
        pytest.skip("postgres marker was not selected")

    project_name = f"acquire-pytest-postgres-{os.getpid()}"
    postgres_port = os.environ.get("ACQUIRE_POSTGRES_TEST_PORT")
    if postgres_port is None:
        postgres_port = _get_available_local_port()
    compose_env = {
        "ACQUIRE_POSTGRES_TEST_PORT": postgres_port,
        "POSTGRES_DB": os.environ.get("POSTGRES_DB", "acquire"),
        "POSTGRES_USER": os.environ.get("POSTGRES_USER", "acquire"),
        "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD", "acquire"),
    }
    previous_env = {key: os.environ.get(key) for key in compose_env}
    os.environ.update(compose_env)
    try:
        _run_docker_compose(project_name, "up", "-d", "postgres", include_test_override=True)
        postgres_url = "postgresql+psycopg://{}:{}@127.0.0.1:{}/{}".format(
            quote(compose_env["POSTGRES_USER"], safe=""),
            quote(compose_env["POSTGRES_PASSWORD"], safe=""),
            postgres_port,
            compose_env["POSTGRES_DB"],
        )
        engine = sqlalchemy.create_engine(postgres_url)
        try:
            deadline = time.monotonic() + 60
            while True:
                try:
                    with engine.connect() as connection:
                        connection.execute(sqlalchemy.text("select 1"))
                    break
                except sqlalchemy.exc.DBAPIError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(1)
        finally:
            engine.dispose()
        yield postgres_url
    finally:
        _cleanup_docker_compose(project_name, "down", "--volumes", include_test_override=True)
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session")
def e2e_base_url(pytestconfig):
    configured_url = os.environ.get("ACQUIRE_E2E_URL")
    if configured_url:
        yield configured_url
        return
    if not _is_marker_selected(pytestconfig, "e2e"):
        pytest.skip("e2e marker was not selected")

    project_name = f"acquire-pytest-e2e-{os.getpid()}"
    ui_port = os.environ.get("ACQUIRE_E2E_PORT", "19000")
    previous_port = os.environ.get("ACQUIRE_UI_PORT")
    os.environ["ACQUIRE_UI_PORT"] = ui_port
    try:
        _run_docker_compose(
            project_name,
            "--profile",
            "client-build",
            "run",
            "--rm",
            "client-assets",
        )
        _run_docker_compose(
            project_name,
            "up",
            "--build",
            "-d",
            "mysql",
            "python-gateway",
        )
        _run_docker_compose(
            project_name,
            "run",
            "--rm",
            "python-gateway",
            "sh",
            "-c",
            "for i in $(seq 1 30); do "
            "test -S /var/run/mysqld/mysqld.sock && exec python initialize_database.py; "
            "sleep 1; "
            "done; "
            "echo 'MySQL socket was not ready at /var/run/mysqld/mysqld.sock' >&2; "
            "exit 1",
        )
        yield f"http://127.0.0.1:{ui_port}/"
    finally:
        _cleanup_docker_compose(
            project_name,
            "--profile",
            "client-build",
            "rm",
            "-f",
            "-v",
            "client-assets",
            "client-enums",
        )
        _cleanup_docker_compose(project_name, "--profile", "client-build", "down", "--volumes")
        if previous_port is None:
            os.environ.pop("ACQUIRE_UI_PORT", None)
        else:
            os.environ["ACQUIRE_UI_PORT"] = previous_port


@pytest.fixture
def logs_to_games_without_database(monkeypatch):
    monkeypatch.delitem(sys.modules, "logs_to_games", raising=False)

    sqlalchemy = types.ModuleType("sqlalchemy")
    sqlalchemy.sql = types.SimpleNamespace(text=lambda query: query)
    monkeypatch.setitem(sys.modules, "orm", types.ModuleType("orm"))
    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy)
    monkeypatch.setitem(sys.modules, "sqlalchemy.sql", sqlalchemy.sql)

    try:
        yield importlib.import_module("logs_to_games")
    finally:
        sys.modules.pop("logs_to_games", None)
