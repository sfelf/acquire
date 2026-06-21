import importlib
import os
import subprocess
import sys
import types
from pathlib import Path
from urllib.parse import quote

import pytest

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
            "legacy-node",
            "up",
            "--build",
            "-d",
            "mysql",
            "python-server",
            "node-gateway",
        )
        _run_docker_compose(
            project_name,
            "run",
            "--rm",
            "python-server",
            "python",
            "initialize_database.py",
        )
        yield f"http://127.0.0.1:{ui_port}/"
    finally:
        _cleanup_docker_compose(project_name, "--profile", "legacy-node", "down", "--volumes")
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
