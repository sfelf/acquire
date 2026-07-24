import importlib
import sys
import types
from pathlib import Path

import pytest

import acquire

pytestmark = pytest.mark.unit


class Config:
    def __init__(self, path):
        self.path = path
        self.main_options = {}

    def set_main_option(self, name, value):
        self.main_options[name] = value


class Connection:
    def __init__(self, lookup_rows):
        self.lookup_rows = lookup_rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query):
        table_name = query.removeprefix("select name from ")
        return [(name,) for name in self.lookup_rows.get(table_name, set())]


class Engine:
    def __init__(self, lookup_rows=None):
        self.lookup_rows = lookup_rows or {}

    def connect(self):
        return Connection(self.lookup_rows)


class Inspector:
    def __init__(self, table_names, columns=None):
        self.table_names = table_names
        self.columns = columns or {}

    def get_table_names(self):
        return self.table_names

    def get_columns(self, table_name):
        return [{"name": column_name} for column_name in self.columns.get(table_name, set())]


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
    orm = types.ModuleType("acquire.orm")
    orm.engine = Engine()
    sqlalchemy = types.ModuleType("sqlalchemy")
    sqlalchemy.inspect = lambda engine: Inspector([])
    sqlalchemy.text = lambda query: query
    monkeypatch.setitem(sys.modules, "alembic", alembic)
    monkeypatch.setitem(sys.modules, "alembic.command", command)
    monkeypatch.setitem(sys.modules, "alembic.config", config)
    monkeypatch.setitem(sys.modules, "acquire.orm", orm)
    monkeypatch.setattr(acquire, "orm", orm, raising=False)
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
    setup_database.orm.engine = Engine(setup_database.BASELINE_LOOKUP_ROWS)
    monkeypatch.setattr(
        sqlalchemy,
        "inspect",
        lambda engine: Inspector(
            list(setup_database.BASELINE_TABLES),
            setup_database.BASELINE_COLUMNS,
        ),
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
    assert [call[2] for call in calls] == [setup_database.BASELINE_REVISION, "head"]
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
    monkeypatch.setattr(
        sqlalchemy,
        "inspect",
        lambda engine: Inspector(table_names, setup_database.BASELINE_COLUMNS),
    )
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


def test_setup_database_does_not_stamp_schema_with_missing_columns(
    setup_database_module,
    monkeypatch,
):
    setup_database, command, sqlalchemy = setup_database_module
    calls = []
    setup_database.orm.engine = Engine(setup_database.BASELINE_LOOKUP_ROWS)
    columns = {
        **setup_database.BASELINE_COLUMNS,
        "user": {"user_id", "name"},
    }
    monkeypatch.setattr(
        sqlalchemy,
        "inspect",
        lambda engine: Inspector(list(setup_database.BASELINE_TABLES), columns),
    )
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


def test_setup_database_does_not_stamp_schema_with_missing_lookup_rows(
    setup_database_module,
    monkeypatch,
):
    setup_database, command, sqlalchemy = setup_database_module
    calls = []
    setup_database.orm.engine = Engine(
        {
            **setup_database.BASELINE_LOOKUP_ROWS,
            "rating_type": {"Singles2", "Singles3", "Singles4"},
        }
    )
    monkeypatch.setattr(
        sqlalchemy,
        "inspect",
        lambda engine: Inspector(
            list(setup_database.BASELINE_TABLES),
            setup_database.BASELINE_COLUMNS,
        ),
    )
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
