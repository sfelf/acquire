import contextlib
import importlib
import sys
import types

import pytest


pytestmark = pytest.mark.unit


class FakeColumn:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def desc(self):
        return ("desc", self)


class FakeDeclarativeBase:
    metadata = types.SimpleNamespace(create_all=lambda engine: None)

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeURL:
    def __init__(self, drivername, **kwargs):
        self.drivername = drivername
        self.kwargs = kwargs


def install_fake_sqlalchemy(monkeypatch):
    fake_sqlalchemy = types.ModuleType("sqlalchemy")
    fake_sqlalchemy.create_engine = lambda *args, **kwargs: ("engine", args, kwargs)
    fake_sqlalchemy.Column = FakeColumn
    fake_sqlalchemy.Index = lambda *args, **kwargs: ("index", args, kwargs)
    fake_sqlalchemy.ForeignKey = lambda *args, **kwargs: ("foreign-key", args, kwargs)
    fake_sqlalchemy.String = lambda *args, **kwargs: ("string", args, kwargs)
    fake_sqlalchemy.Text = lambda *args, **kwargs: ("text", args, kwargs)
    fake_sqlalchemy.UniqueConstraint = (
        lambda *args, **kwargs: ("unique", args, kwargs)
    )

    fake_mysql = types.ModuleType("sqlalchemy.dialects.mysql")
    fake_mysql.FLOAT = lambda *args, **kwargs: ("float", args, kwargs)
    fake_mysql.INTEGER = lambda *args, **kwargs: ("integer", args, kwargs)
    fake_mysql.SMALLINT = lambda *args, **kwargs: ("smallint", args, kwargs)
    fake_mysql.TINYINT = lambda *args, **kwargs: ("tinyint", args, kwargs)

    fake_declarative = types.ModuleType("sqlalchemy.ext.declarative")
    fake_declarative.declarative_base = lambda: FakeDeclarativeBase

    fake_engine = types.ModuleType("sqlalchemy.engine")
    fake_engine_url = types.ModuleType("sqlalchemy.engine.url")
    fake_engine_url.URL = FakeURL

    fake_orm = types.ModuleType("sqlalchemy.orm")
    fake_orm.relationship = lambda *args, **kwargs: ("relationship", args, kwargs)
    fake_orm.sessionmaker = lambda bind=None: lambda autoflush=False: None

    fake_sqlalchemy.dialects = types.SimpleNamespace(mysql=fake_mysql)
    fake_sqlalchemy.engine = types.SimpleNamespace(url=fake_engine_url)
    fake_sqlalchemy.ext = types.SimpleNamespace(declarative=fake_declarative)
    fake_sqlalchemy.orm = fake_orm

    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqlalchemy)
    monkeypatch.setitem(sys.modules, "sqlalchemy.dialects", fake_sqlalchemy.dialects)
    monkeypatch.setitem(sys.modules, "sqlalchemy.dialects.mysql", fake_mysql)
    monkeypatch.setitem(sys.modules, "sqlalchemy.engine", fake_engine)
    monkeypatch.setitem(sys.modules, "sqlalchemy.engine.url", fake_engine_url)
    monkeypatch.setitem(sys.modules, "sqlalchemy.ext", fake_sqlalchemy.ext)
    monkeypatch.setitem(sys.modules, "sqlalchemy.ext.declarative", fake_declarative)
    monkeypatch.setitem(sys.modules, "sqlalchemy.orm", fake_orm)


@pytest.fixture
def orm_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "orm", raising=False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    monkeypatch.delenv("MYSQL_SOCKET", raising=False)
    monkeypatch.delenv("MYSQL_USER", raising=False)
    monkeypatch.delenv("MYSQL_AUTH_PLUGIN", raising=False)
    install_fake_sqlalchemy(monkeypatch)

    try:
        yield importlib.import_module("orm")
    finally:
        sys.modules.pop("orm", None)


class TransactionSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_session_scope_commits_and_closes(orm_module, monkeypatch):
    session = TransactionSession()
    monkeypatch.setattr(orm_module, "Session", lambda autoflush: session)

    with orm_module.session_scope() as yielded_session:
        assert yielded_session is session

    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True


def test_engine_uses_default_mysql_settings(orm_module):
    url = orm_module.engine[1][0]

    assert url.drivername == "mysql+mysqlconnector"
    assert url.kwargs == {
        "username": "acquire",
        "password": "acquire",
        "host": "localhost",
        "database": "acquire",
        "query": {"unix_socket": "/var/run/mysqld/mysqld.sock"},
    }
    assert orm_module.engine == (
        "engine",
        (url,),
        {"connect_args": {"auth_plugin": "mysql_native_password"}},
    )


def test_engine_uses_mysql_environment(monkeypatch):
    monkeypatch.delitem(sys.modules, "orm", raising=False)
    monkeypatch.setenv("MYSQL_DATABASE", "custom db")
    monkeypatch.setenv("MYSQL_PASSWORD", "custom password")
    monkeypatch.setenv("MYSQL_SOCKET", "/tmp/mysql.sock")
    monkeypatch.setenv("MYSQL_USER", "custom_user")
    monkeypatch.setenv("MYSQL_AUTH_PLUGIN", "")
    install_fake_sqlalchemy(monkeypatch)

    try:
        orm = importlib.import_module("orm")
        url = orm.engine[1][0]

        assert url.drivername == "mysql+mysqlconnector"
        assert url.kwargs == {
            "username": "custom_user",
            "password": "custom password",
            "host": "localhost",
            "database": "custom db",
            "query": {"unix_socket": "/tmp/mysql.sock"},
        }
        assert orm.engine == (
            "engine",
            (url,),
            {"connect_args": {}},
        )
    finally:
        sys.modules.pop("orm", None)


def test_session_scope_rolls_back_and_closes_on_error(orm_module, monkeypatch):
    session = TransactionSession()
    monkeypatch.setattr(orm_module, "Session", lambda autoflush: session)

    with pytest.raises(RuntimeError, match="boom"):
        with orm_module.session_scope():
            raise RuntimeError("boom")

    assert session.committed is False
    assert session.rolled_back is True
    assert session.closed is True


@pytest.mark.parametrize(
    ("factory", "kwargs", "expected"),
    [
        (
            "Game",
            {
                "game_id": 1,
                "log_time": 100,
                "number": 2,
                "begin_time": 10,
                "end_time": 20,
                "game_state_id": 3,
                "game_mode_id": 4,
            },
            "Game(game_id=1, log_time=100, number=2, begin_time=10, end_time=20, game_state_id=3, game_mode_id=4)",
        ),
        (
            "GameMode",
            {"game_mode_id": 1, "name": "Singles"},
            "GameMode(game_mode_id=1, name='Singles')",
        ),
        (
            "GamePlayer",
            {
                "game_player_id": 1,
                "game_id": 2,
                "player_index": 3,
                "user_id": 4,
                "score": 5,
            },
            "GamePlayer(game_player_id=1, game_id=2, player_index=3, user_id=4, score=5)",
        ),
        (
            "GameState",
            {"game_state_id": 1, "name": "Completed"},
            "GameState(game_state_id=1, name='Completed')",
        ),
        (
            "KeyValue",
            {"key_value_id": 1, "key": "cron", "value": "42"},
            "KeyValue(key_value_id=1, key='cron', value='42')",
        ),
        (
            "Rating",
            {
                "rating_id": 1,
                "user_id": 2,
                "rating_type_id": 3,
                "time": 4,
                "mu": 25.0,
                "sigma": 8.333,
            },
            "Rating(rating_id=1, user_id=2, rating_type_id=3, time=4, mu=25.0, sigma=8.333)",
        ),
        (
            "RatingType",
            {"rating_type_id": 1, "name": "Singles2"},
            "RatingType(rating_type_id=1, name='Singles2')",
        ),
        (
            "Record",
            {"user_id": 1, "encoded": "[[1,0]]"},
            "Record(user_id=1, encoded='[[1,0]]')",
        ),
        (
            "User",
            {"user_id": 1, "name": "alice", "password": "secret"},
            "User(user_id=1, name='alice', password='secret')",
        ),
    ],
)
def test_model_repr_strings(orm_module, factory, kwargs, expected):
    assert repr(getattr(orm_module, factory)(**kwargs)) == expected


class FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.filters = {}
        self.orderings = []
        self.limit_value = None

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def order_by(self, *args):
        self.orderings.extend(args)
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def scalar(self):
        key = self.session.key_for(self.model, self.filters)
        self.session.scalar_queries.append((self.model, dict(self.filters)))
        return self.session.results.get(key)


class LookupSession:
    def __init__(self):
        self.results = {}
        self.added = []
        self.queries = []
        self.scalar_queries = []

    def key_for(self, model, filters):
        return (model, tuple(sorted(filters.items(), key=lambda item: item[0])))

    def set_result(self, model, result, **filters):
        self.results[self.key_for(model, filters)] = result

    def query(self, model):
        self.queries.append(model)
        return FakeQuery(self, model)

    def add(self, item):
        self.added.append(item)


def test_lookup_get_game_creates_and_caches_missing_game(orm_module):
    session = LookupSession()
    lookup = orm_module.Lookup(session)

    first = lookup.get_game(100, 7)
    second = lookup.get_game(100, 7)

    assert first is second
    assert isinstance(first, orm_module.Game)
    assert first.log_time == 100
    assert first.number == 7
    assert session.added == [first]
    assert session.queries == [orm_module.Game]


def test_lookup_get_game_returns_and_caches_existing_game(orm_module):
    session = LookupSession()
    game = orm_module.Game(game_id=1, log_time=100, number=7)
    session.set_result(orm_module.Game, game, log_time=100, number=7)
    lookup = orm_module.Lookup(session)

    assert lookup.get_game(100, 7) is game
    assert lookup.get_game(100, 7) is game
    assert session.added == []
    assert session.queries == [orm_module.Game]


def test_lookup_get_game_mode_and_state_and_rating_type_use_existing_rows(
    orm_module,
):
    session = LookupSession()
    game_mode = orm_module.GameMode(name="Singles")
    game_state = orm_module.GameState(name="Completed")
    rating_type = orm_module.RatingType(name="Singles2")
    session.set_result(orm_module.GameMode, game_mode, name="Singles")
    session.set_result(orm_module.GameState, game_state, name="Completed")
    session.set_result(orm_module.RatingType, rating_type, name="Singles2")
    lookup = orm_module.Lookup(session)

    assert lookup.get_game_mode("Singles") is game_mode
    assert lookup.get_game_mode("Singles") is game_mode
    assert lookup.get_game_state("Completed") is game_state
    assert lookup.get_game_state("Completed") is game_state
    assert lookup.get_rating_type("Singles2") is rating_type
    assert lookup.get_rating_type("Singles2") is rating_type
    assert session.queries == [
        orm_module.GameMode,
        orm_module.GameState,
        orm_module.RatingType,
    ]


def test_lookup_get_game_player_queries_when_game_has_id(orm_module):
    session = LookupSession()
    game = orm_module.Game(game_id=10, log_time=100, number=7)
    game_player = orm_module.GamePlayer(game=game, player_index=2)
    session.set_result(orm_module.GamePlayer, game_player, game_id=10, player_index=2)
    lookup = orm_module.Lookup(session)

    assert lookup.get_game_player(game, 2) is game_player
    assert lookup.get_game_player(game, 2) is game_player
    assert session.added == []
    assert session.queries == [orm_module.GamePlayer]


def test_lookup_get_game_player_creates_missing_player(orm_module):
    session = LookupSession()
    game = orm_module.Game(game_id=None, log_time=100, number=7)
    lookup = orm_module.Lookup(session)

    game_player = lookup.get_game_player(game, 1)

    assert isinstance(game_player, orm_module.GamePlayer)
    assert game_player.game is game
    assert game_player.player_index == 1
    assert session.added == [game_player]
    assert session.queries == []


def test_lookup_get_key_value_creates_and_caches_missing_row(orm_module):
    session = LookupSession()
    lookup = orm_module.Lookup(session)

    key_value = lookup.get_key_value("cron last offset")

    assert isinstance(key_value, orm_module.KeyValue)
    assert key_value.key == "cron last offset"
    assert lookup.get_key_value("cron last offset") is key_value
    assert session.added == [key_value]
    assert session.queries == [orm_module.KeyValue]


def test_lookup_get_user_creates_and_caches_missing_user(orm_module):
    session = LookupSession()
    lookup = orm_module.Lookup(session)

    user = lookup.get_user("alice")

    assert isinstance(user, orm_module.User)
    assert user.name == "alice"
    assert lookup.get_user("alice") is user
    assert session.added == [user]
    assert session.queries == [orm_module.User]


def test_lookup_get_user_returns_existing_user(orm_module):
    session = LookupSession()
    user = orm_module.User(user_id=1, name="alice")
    session.set_result(orm_module.User, user, name="alice")
    lookup = orm_module.Lookup(session)

    assert lookup.get_user("alice") is user
    assert lookup.get_user("alice") is user
    assert session.added == []
    assert session.queries == [orm_module.User]


def test_lookup_get_rating_queries_latest_rating_for_persisted_user(orm_module):
    session = LookupSession()
    user = orm_module.User(user_id=1, name="alice")
    rating_type = orm_module.RatingType(name="Singles2")
    rating = orm_module.Rating(user=user, rating_type=rating_type)
    session.set_result(orm_module.Rating, rating, user=user, rating_type=rating_type)
    lookup = orm_module.Lookup(session)

    assert lookup.get_rating(user, rating_type) is rating
    assert lookup.get_rating(user, rating_type) is rating
    assert session.added == []
    assert session.queries == [orm_module.Rating]


def test_lookup_get_rating_skips_query_for_unpersisted_user(orm_module):
    session = LookupSession()
    lookup = orm_module.Lookup(session)

    assert lookup.get_rating(
        orm_module.User(user_id=None, name="alice"),
        orm_module.RatingType(name="Singles2"),
    ) is None
    assert session.queries == []


def test_lookup_add_rating_updates_rating_cache(orm_module):
    lookup = orm_module.Lookup(LookupSession())
    user = orm_module.User(name="alice")
    rating_type = orm_module.RatingType(name="Singles2")
    rating = orm_module.Rating(user=user, rating_type=rating_type)

    lookup.add_rating(rating)

    assert lookup.get_rating(user, rating_type) is rating


def test_lookup_get_record_queries_and_caches_existing_record(orm_module):
    session = LookupSession()
    user = orm_module.User(user_id=1, name="alice")
    record = orm_module.Record(user=user, encoded="[]")
    session.set_result(orm_module.Record, record, user=user)
    lookup = orm_module.Lookup(session)

    assert lookup.get_record(user) is record
    assert lookup.get_record(user) is record
    assert session.added == []
    assert session.queries == [orm_module.Record]


def test_lookup_get_record_skips_query_for_unpersisted_user(orm_module):
    session = LookupSession()
    lookup = orm_module.Lookup(session)

    assert lookup.get_record(orm_module.User(user_id=None, name="alice")) is None
    assert session.queries == []


def test_lookup_add_record_updates_record_cache(orm_module):
    lookup = orm_module.Lookup(LookupSession())
    user = orm_module.User(name="alice")
    record = orm_module.Record(user=user, encoded="[]")

    lookup.add_record(record)

    assert lookup.get_record(user) is record
