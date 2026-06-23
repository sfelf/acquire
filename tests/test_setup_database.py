import importlib
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


class Config:
    def __init__(self, path):
        self.path = path
        self.main_options = {}

    def set_main_option(self, name, value):
        self.main_options[name] = value


@pytest.fixture
def setup_database_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "setup_database", raising=False)

    alembic = types.ModuleType("alembic")
    command = types.ModuleType("alembic.command")
    command.upgrade = lambda config, revision: None
    config = types.ModuleType("alembic.config")
    config.Config = Config
    alembic.command = command
    monkeypatch.setitem(sys.modules, "alembic", alembic)
    monkeypatch.setitem(sys.modules, "alembic.command", command)
    monkeypatch.setitem(sys.modules, "alembic.config", config)

    try:
        yield importlib.import_module("setup_database"), command
    finally:
        sys.modules.pop("setup_database", None)


def test_setup_database_uses_repository_alembic_config(setup_database_module):
    setup_database, _ = setup_database_module

    config = setup_database.alembic_config()

    assert Path(config.path).name == "alembic.ini"
    assert Path(config.path).parent == Path(__file__).resolve().parents[1]
    assert Path(config.main_options["script_location"]).name == "migrations"
    assert Path(config.main_options["script_location"]).parent == Path(
        __file__
    ).resolve().parents[1]


def test_setup_database_upgrades_to_head(setup_database_module, monkeypatch):
    setup_database, command = setup_database_module
    calls = []
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda config, revision: calls.append((config, revision)),
    )

    setup_database.main()

    assert len(calls) == 1
    config, revision = calls[0]
    assert Path(config.path).name == "alembic.ini"
    assert revision == "head"
