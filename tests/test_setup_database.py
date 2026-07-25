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
    monkeypatch.delitem(sys.modules, "acquire.setup_database", raising=False)
    monkeypatch.delattr(acquire, "setup_database", raising=False)

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
        yield importlib.import_module("acquire.setup_database"), command, sqlalchemy
    finally:
        sys.modules.pop("setup_database", None)
        sys.modules.pop("acquire.setup_database", None)
        monkeypatch.delattr(acquire, "setup_database", raising=False)


def test_setup_database_uses_packaged_alembic_config(setup_database_module):
    setup_database, _, _ = setup_database_module

    config = setup_database.alembic_config()

    assert Path(config.path).name == "alembic.ini"
    assert Path(config.path).parent == Path(acquire.__file__).resolve().parent
    assert Path(config.main_options["script_location"]).name == "migrations"
    assert Path(config.main_options["script_location"]).parent == Path(
        acquire.__file__
    ).resolve().parent


def test_setup_database_rejects_install_without_packaged_migrations(
    setup_database_module,
    monkeypatch,
    tmp_path,
):
    setup_database, _, _ = setup_database_module
    monkeypatch.setattr(setup_database.resources, "files", lambda package: tmp_path)

    with pytest.raises(
        RuntimeError,
        match="requires installed migration resources",
    ):
        setup_database.alembic_config()


def test_setup_database_rejects_package_with_config_but_no_migrations(
    setup_database_module,
    monkeypatch,
    tmp_path,
):
    setup_database, _, _ = setup_database_module
    (tmp_path / "alembic.ini").write_text("[alembic]\n")
    monkeypatch.setattr(setup_database.resources, "files", lambda package: tmp_path)

    with pytest.raises(
        RuntimeError,
        match="requires installed migration resources",
    ):
        setup_database.alembic_config()


def test_setup_database_upgrades_to_head(setup_database_module, monkeypatch):
    setup_database, command, _ = setup_database_module
    calls = []
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda config, revision: calls.append((config, revision)),
    )

    setup_database.run_setup()

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

    setup_database.run_setup()

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

    setup_database.run_setup()

    assert calls == [("upgrade", "head")]


def test_setup_database_does_not_stamp_schema_with_extra_table(
    setup_database_module,
    monkeypatch,
):
    setup_database, command, sqlalchemy = setup_database_module
    calls = []
    table_names = [*setup_database.BASELINE_TABLES, "unexpected"]
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

    setup_database.run_setup()

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

    setup_database.run_setup()

    assert calls == [("upgrade", "head")]


def test_setup_database_propagates_inspection_failure_without_upgrade(
    setup_database_module,
    monkeypatch,
):
    setup_database, command, sqlalchemy = setup_database_module
    calls = []

    def raise_inspection_error(engine):
        raise RuntimeError("inspection failed")

    monkeypatch.setattr(sqlalchemy, "inspect", raise_inspection_error)
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda config, revision: calls.append(("upgrade", revision)),
    )

    with pytest.raises(RuntimeError, match="inspection failed"):
        setup_database.run_setup()

    assert calls == []


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

    setup_database.run_setup()

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

    setup_database.run_setup()

    assert calls == [("upgrade", "head")]


def test_setup_database_main_returns_success(setup_database_module, monkeypatch):
    setup_database, _, _ = setup_database_module
    calls = []
    monkeypatch.setattr(setup_database, "run_setup", lambda: calls.append("setup"))

    result = setup_database.main([])

    assert result == 0
    assert calls == ["setup"]


@pytest.mark.parametrize(
    "sensitive_argument",
    [
        "postgresql://private-user:private-password@private-host/db",
        r"postgresql:\/\/private-user\:private-password\@private-host\/db",
        "postgresql%3A%2F%2Fprivate-user%3Aprivate-password%40private-host%2Fdb",
        (
            "postgresql%253A%252F%252Fprivate-user%253A"
            "private-password%2540private-host%252Fdb"
        ),
    ],
)
def test_setup_database_main_rejects_arguments_without_reflecting_values(
    setup_database_module,
    capsys,
    sensitive_argument,
):
    setup_database, _, _ = setup_database_module

    with pytest.raises(SystemExit) as exit_info:
        setup_database.main([sensitive_argument])

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert captured.out == ""
    assert captured.err == "error: invalid arguments\n"
    assert sensitive_argument not in captured.err


def test_setup_database_main_sanitizes_setup_failures(
    setup_database_module,
    monkeypatch,
    capsys,
):
    setup_database, _, _ = setup_database_module
    sensitive_error = "postgresql://private-user:private-password@private-host/db"

    def fail_setup():
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(setup_database, "run_setup", fail_setup)

    result = setup_database.main([])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: database setup failed\n"
    assert sensitive_error not in captured.err
