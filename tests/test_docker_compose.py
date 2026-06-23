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
    assert "python-server" not in services
    assert "node-gateway" not in services


def test_compose_does_not_define_legacy_node_profile():
    services = _load_compose_services()

    for service in services.values():
        assert "legacy-node" not in service.get("profiles", [])


def test_python_gateway_does_not_depend_on_client_asset_build():
    services = _load_compose_services()

    assert services["python-gateway"]["depends_on"] == {"mysql": {"condition": "service_healthy"}}


def test_python_gateway_explains_missing_client_assets():
    services = _load_compose_services()

    assert "client-build" in services["python-gateway"]["command"]


def test_e2e_fixture_uses_alembic_database_setup():
    fixture_text = (REPO_DIR / "tests" / "conftest.py").read_text()

    assert "python setup_database.py" in fixture_text
    assert "python initialize_database.py" not in fixture_text


def test_compose_defines_postgres_for_marker_tests():
    services = _load_compose_services()

    assert services["postgres"]["image"] == "postgres:17"
    assert services["postgres"]["profiles"] == ["postgres"]
    assert services["postgres"]["healthcheck"]["test"][0] == "CMD-SHELL"
    assert "POSTGRES_DB" in services["postgres"]["environment"]
