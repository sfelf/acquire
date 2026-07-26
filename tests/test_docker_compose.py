from pathlib import Path

import yaml

REPO_DIR = Path(__file__).resolve().parents[1]


def _load_compose_services():
    with (REPO_DIR / "docker-compose.yml").open() as compose_file:
        return yaml.safe_load(compose_file)["services"]


def test_default_compose_runtime_excludes_node_services():
    services = _load_compose_services()

    assert "profiles" not in services["python-gateway"]
    assert services["client-enums"]["profiles"] == ["client-build"]
    assert services["client-assets"]["profiles"] == ["client-build"]
    assert "mysql" not in services
    assert "python-server" not in services
    assert "node-gateway" not in services


def test_compose_does_not_define_legacy_node_profile():
    services = _load_compose_services()

    for service in services.values():
        assert "legacy-node" not in service.get("profiles", [])


def test_python_gateway_does_not_depend_on_client_asset_build():
    services = _load_compose_services()

    assert services["python-gateway"]["depends_on"] == {
        "postgres": {"condition": "service_healthy"}
    }


def test_python_gateway_explains_missing_client_assets():
    services = _load_compose_services()

    assert "client-build" in services["python-gateway"]["command"]


def test_python_gateway_uses_installed_command_and_explicit_static_roots():
    services = _load_compose_services()
    gateway = services["python-gateway"]
    command = gateway["command"]

    assert gateway["working_dir"] == "/app"
    assert "acquire-http-server" in command
    assert "--main-static-root /app/client/main" in command
    assert "--stats-static-root /app/client/stats" in command
    assert "http_server.py" not in command


def test_client_asset_helper_uses_modern_node_and_npm_scripts():
    services = _load_compose_services()
    client_assets = services["client-assets"]
    command = client_assets["command"]

    assert client_assets["image"] == "node:22-bookworm-slim"
    assert client_assets["working_dir"] == "/app/client"
    assert "node-modules:/app/client/node_modules" in client_assets["volumes"]
    assert "npm ci" in command
    assert "npm run build:css" in command
    assert "npm run build:js" in command
    assert "npm run verify:client" in command
    assert "node-sass" not in command
    assert "webpack" not in command


def test_gateway_checks_the_complete_client_output_set():
    services = _load_compose_services()
    command = services["python-gateway"]["command"]

    for output in (
        "client/main/css/main.css",
        "client/stats/css/stats.css",
        "client/main/js/enums.js",
        "client/main/js/main.js",
        "client/main/js/main.js.map",
    ):
        assert f"/app/{output}" in command


def test_client_enum_helper_uses_packaged_module_with_absolute_paths():
    services = _load_compose_services()
    client_enums = services["client-enums"]
    command = client_enums["command"]

    assert command == [
        "acquire-generate-enums",
        "js",
        "development",
        "--client-source-root",
        "/app/client/main/js",
        "--output",
        "/app/client/main/js/enums.js",
    ]


def test_e2e_fixture_uses_alembic_database_setup():
    fixture_text = (REPO_DIR / "tests" / "conftest.py").read_text()

    assert '"acquire-setup-database"' in fixture_text
    assert '"setup_database.py"' not in fixture_text
    assert "python initialize_database.py" not in fixture_text
    assert '"postgres"' in fixture_text
    assert "mysql_test_url" not in fixture_text
    assert "ACQUIRE_MYSQL" not in fixture_text


def test_compose_defines_postgres_as_default_database():
    services = _load_compose_services()

    assert services["postgres"]["image"] == "postgres:17"
    assert "profiles" not in services["postgres"]
    assert services["postgres"]["healthcheck"]["test"][0] == "CMD-SHELL"
    assert "POSTGRES_DB" in services["postgres"]["environment"]
