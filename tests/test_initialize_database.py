import importlib
import sys
import types

import pytest


pytestmark = pytest.mark.unit


class SessionScope:
    def __init__(self, added):
        self.added = added

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def add(self, row):
        self.added.append(row)


class Row:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return type(self) is type(other) and self.name == other.name

    def __repr__(self):
        return f"{type(self).__name__}(name={self.name!r})"


class GameMode(Row):
    pass


class GameState(Row):
    pass


class RatingType(Row):
    pass


class Metadata:
    def __init__(self):
        self.create_all_calls = []

    def create_all(self, engine):
        self.create_all_calls.append(engine)


@pytest.fixture
def initialize_database_with_stubbed_orm(monkeypatch):
    monkeypatch.delitem(sys.modules, "initialize_database", raising=False)

    added = []
    orm = types.ModuleType("orm")
    orm.engine = object()
    orm.Base = types.SimpleNamespace(metadata=Metadata())
    orm.session_scope = lambda: SessionScope(added)
    orm.GameMode = GameMode
    orm.GameState = GameState
    orm.RatingType = RatingType
    monkeypatch.setitem(sys.modules, "orm", orm)

    try:
        yield importlib.import_module("initialize_database"), orm, added
    finally:
        sys.modules.pop("initialize_database", None)


def test_initialize_database_resets_schema_creates_tables_and_seeds_rows(
    initialize_database_with_stubbed_orm,
    monkeypatch,
):
    initialize_database, orm, added = initialize_database_with_stubbed_orm
    subprocess_calls = []
    monkeypatch.setattr(initialize_database.subprocess, "call", subprocess_calls.append)

    initialize_database.main()

    assert subprocess_calls == [
        [
            "mysql",
            "--socket",
            "/var/run/mysqld/mysqld.sock",
            "-u",
            "root",
            "-proot",
            "-e",
            "drop schema if exists `acquire`; create schema `acquire` default character set utf8mb4 collate utf8mb4_bin;",
        ]
    ]
    assert orm.Base.metadata.create_all_calls == [orm.engine]
    assert added == [
        GameMode(name="Singles"),
        GameMode(name="Teams"),
        GameState(name="Starting"),
        GameState(name="StartingFull"),
        GameState(name="InProgress"),
        GameState(name="Completed"),
        RatingType(name="Singles2"),
        RatingType(name="Singles3"),
        RatingType(name="Singles4"),
        RatingType(name="Teams"),
    ]


def test_initialize_database_uses_mysql_environment(
    initialize_database_with_stubbed_orm,
    monkeypatch,
):
    initialize_database, _, _ = initialize_database_with_stubbed_orm
    subprocess_calls = []
    monkeypatch.setattr(initialize_database.subprocess, "call", subprocess_calls.append)
    monkeypatch.setenv("MYSQL_DATABASE", "custom_acquire")
    monkeypatch.setenv("MYSQL_ROOT_PASSWORD", "custom-root")
    monkeypatch.setenv("MYSQL_SOCKET", "/tmp/mysql.sock")

    initialize_database.main()

    assert subprocess_calls[0] == [
        "mysql",
        "--socket",
        "/tmp/mysql.sock",
        "-u",
        "root",
        "-pcustom-root",
        "-e",
        "drop schema if exists `custom_acquire`; create schema `custom_acquire` default character set utf8mb4 collate utf8mb4_bin;",
    ]
