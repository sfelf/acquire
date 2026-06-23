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


class Inspector:
    def __init__(self, table_names):
        self.table_names = table_names

    def get_table_names(self):
        return self.table_names


@pytest.fixture
def setup_database_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "setup_database", raising=False)

    alembic = types.ModuleType("alembic")
    command = types.ModuleType("alembic.command")
    command.stamp = lambda config, revision: None
    command.upgrade = lambda config, revision: None
    config = types.ModuleType("alembic.config")
    config.Config = Config
    alembic.command = command
    orm = types.ModuleType("orm")
    orm.engine = object()
    sqlalchemy = types.ModuleType("sqlalchemy")
    sqlalchemy.inspect = lambda engine: Inspector([])
    monkeypatch.setitem(sys.modules, "alembic", alembic)
    monkeypatch.setitem(sys.modules, "alembic.command", command)
    monkeypatch.setitem(sys.modules, "alembic.config", config)
    monkeypatch.setitem(sys.modules, "orm", orm)
    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy)

    try:
        yield importlib.import_module("setup_database"), command, sqlalchemy
    finally:
        sys.modules.pop("setup_database", None)


def test_setup_database_uses_repository_alembic_config(setup_database_module):
    setup_database, _, _ = setup_database_module

    config = setup_database.alembic_config()

    assert Path(config.path).name == "alembic.ini"
    assert Path(config.path).parent == Path(__file__).resolve().parents[1]
    assert Path(config.main_options["script_location"]).name == "migrations"
    assert Path(config.main_options["script_location"]).parent == Path(
        __file__
    ).resolve().parents[1]


def test_setup_database_upgrades_to_head(setup_database_module, monkeypatch):
    setup_database, command, _ = setup_database_module
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


def test_setup_database_stamps_unversioned_legacy_schema(setup_database_module, monkeypatch):
    setup_database, command, sqlalchemy = setup_database_module
    calls = []
    monkeypatch.setattr(
        sqlalchemy,
        "inspect",
        lambda engine: Inspector(list(setup_database.BASELINE_TABLES)),
    )
    monkeypatch.setattr(
        command,
        "stamp",
        lambda config, revision: calls.append(("stamp", config, revision)),
    )
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda config, revision: calls.append(("upgrade", config, revision)),
    )

    setup_database.main()

    assert [call[0] for call in calls] == ["stamp", "upgrade"]
    assert [call[2] for call in calls] == ["head", "head"]
    assert calls[0][1] is calls[1][1]


def test_setup_database_does_not_stamp_empty_schema(setup_database_module, monkeypatch):
    setup_database, command, sqlalchemy = setup_database_module
    calls = []
    monkeypatch.setattr(sqlalchemy, "inspect", lambda engine: Inspector([]))
    monkeypatch.setattr(
        command,
        "stamp",
        lambda config, revision: calls.append(("stamp", revision)),
    )
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda config, revision: calls.append(("upgrade", revision)),
    )

    setup_database.main()

    assert calls == [("upgrade", "head")]


def test_setup_database_does_not_stamp_already_versioned_schema(
    setup_database_module,
    monkeypatch,
):
    setup_database, command, sqlalchemy = setup_database_module
    calls = []
    table_names = [*setup_database.BASELINE_TABLES, "alembic_version"]
    monkeypatch.setattr(sqlalchemy, "inspect", lambda engine: Inspector(table_names))
    monkeypatch.setattr(
        command,
        "stamp",
        lambda config, revision: calls.append(("stamp", revision)),
    )
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda config, revision: calls.append(("upgrade", revision)),
    )

    setup_database.main()

    assert calls == [("upgrade", "head")]
