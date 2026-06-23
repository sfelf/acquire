import importlib
import io
import sys
import time
from pathlib import Path

import pytest
import sqlalchemy
import ujson
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.mysql
REPO_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def real_orm_module():
    sys.modules.pop("orm", None)
    try:
        yield importlib.import_module("orm")
    finally:
        sys.modules.pop("orm", None)


@pytest.fixture
def real_cron_module(real_orm_module):
    sys.modules.pop("cron", None)
    try:
        yield importlib.import_module("cron")
    finally:
        sys.modules.pop("cron", None)


@pytest.fixture
def real_auth_module(real_orm_module):
    sys.modules.pop("auth", None)
    try:
        yield importlib.import_module("auth")
    finally:
        sys.modules.pop("auth", None)


@pytest.fixture
def mysql_engine(mysql_test_url):
    engine = sqlalchemy.create_engine(mysql_test_url)
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
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def empty_mysql_schema(mysql_engine, real_orm_module):
    drop_application_schema(mysql_engine, real_orm_module)
    yield
    drop_application_schema(mysql_engine, real_orm_module)


def drop_application_schema(mysql_engine, orm):
    orm.Base.metadata.drop_all(mysql_engine)
    with mysql_engine.begin() as connection:
        connection.execute(sqlalchemy.text("drop table if exists alembic_version"))


def seed_lookup_rows(session, orm):
    session.add_all(
        [
            orm.GameMode(name="Singles"),
            orm.GameMode(name="Teams"),
            orm.GameState(name="Starting"),
            orm.GameState(name="StartingFull"),
            orm.GameState(name="InProgress"),
            orm.GameState(name="Completed"),
            orm.RatingType(name="Singles2"),
            orm.RatingType(name="Singles3"),
            orm.RatingType(name="Singles4"),
            orm.RatingType(name="Teams"),
        ]
    )
    session.flush()


def _table_names(mysql_engine):
    return set(sqlalchemy.inspect(mysql_engine).get_table_names())


def _app_table_names(mysql_engine):
    return _table_names(mysql_engine) - {"alembic_version"}


def _alembic_config(connection):
    config = Config(str(REPO_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def make_mysql_session(mysql_engine):
    return sessionmaker(bind=mysql_engine, autoflush=False)()


def test_orm_metadata_creates_expected_mysql_tables(
    mysql_engine,
    real_orm_module,
    empty_mysql_schema,
):
    real_orm_module.Base.metadata.create_all(mysql_engine)

    assert _table_names(mysql_engine) == {
        "game",
        "game_mode",
        "game_player",
        "game_state",
        "key_value",
        "rating",
        "rating_type",
        "record",
        "user",
    }

    inspector = sqlalchemy.inspect(mysql_engine)
    assert {column["name"] for column in inspector.get_columns("game")} == {
        "game_id",
        "log_time",
        "number",
        "begin_time",
        "end_time",
        "game_state_id",
        "game_mode_id",
    }
    assert ("rating_type_id", "user_id") in {
        tuple(sorted(index["column_names"])) for index in inspector.get_indexes("rating")
    }


def test_alembic_baseline_matches_current_orm_schema_against_mysql(
    mysql_engine,
    real_orm_module,
    empty_mysql_schema,
):
    with mysql_engine.begin() as connection:
        command.upgrade(_alembic_config(connection), "head")

    inspector = sqlalchemy.inspect(mysql_engine)
    assert _app_table_names(mysql_engine) == {
        "game",
        "game_mode",
        "game_player",
        "game_state",
        "key_value",
        "rating",
        "rating_type",
        "record",
        "user",
    }
    with mysql_engine.connect() as connection:
        version = connection.execute(sqlalchemy.text("select version_num from alembic_version"))
        assert version.scalar_one() == "20260622_0001"

    assert _column_contract(inspector, "game") == [
        ("game_id", False, True),
        ("log_time", False, False),
        ("number", False, False),
        ("begin_time", True, False),
        ("end_time", True, False),
        ("game_state_id", False, False),
        ("game_mode_id", False, False),
    ]
    assert _column_contract(inspector, "game_player") == [
        ("game_player_id", False, True),
        ("game_id", False, False),
        ("player_index", False, False),
        ("user_id", False, False),
        ("score", True, False),
    ]
    assert _column_contract(inspector, "key_value") == [
        ("key_value_id", False, True),
        ("key", False, False),
        ("value", False, False),
    ]
    assert _column_contract(inspector, "rating") == [
        ("rating_id", False, True),
        ("user_id", False, False),
        ("rating_type_id", False, False),
        ("time", False, False),
        ("mu", False, False),
        ("sigma", False, False),
    ]
    assert _column_contract(inspector, "record") == [
        ("user_id", False, True),
        ("encoded", False, False),
    ]
    assert _column_contract(inspector, "user") == [
        ("user_id", False, True),
        ("name", False, False),
        ("password", True, False),
    ]
    assert _unique_contract(inspector) == {
        "game": {("log_time", "number")},
        "game_mode": {("name",)},
        "game_player": {("game_id", "player_index")},
        "game_state": {("name",)},
        "key_value": {("key",)},
        "rating_type": {("name",)},
        "user": {("name",)},
    }
    assert _foreign_key_contract(inspector) == {
        "game": {
            (("game_mode_id",), "game_mode", ("game_mode_id",)),
            (("game_state_id",), "game_state", ("game_state_id",)),
        },
        "game_player": {
            (("game_id",), "game", ("game_id",)),
            (("user_id",), "user", ("user_id",)),
        },
        "rating": {
            (("rating_type_id",), "rating_type", ("rating_type_id",)),
            (("user_id",), "user", ("user_id",)),
        },
        "record": {
            (("user_id",), "user", ("user_id",)),
        },
    }
    assert ("end_time",) in {
        tuple(index["column_names"]) for index in inspector.get_indexes("game")
    }
    assert ("user_id", "rating_type_id") in {
        tuple(index["column_names"]) for index in inspector.get_indexes("rating")
    }
    assert _table_collation_contract(inspector) == {
        "game": "utf8mb4_bin",
        "game_mode": "utf8mb4_bin",
        "game_player": "utf8mb4_bin",
        "game_state": "utf8mb4_bin",
        "key_value": "utf8mb4_bin",
        "rating": "utf8mb4_bin",
        "rating_type": "utf8mb4_bin",
        "record": "utf8mb4_bin",
        "user": "utf8mb4_bin",
    }

    session = make_mysql_session(mysql_engine)
    try:
        session.add(real_orm_module.User(name="Alice", password=None))
        session.add(real_orm_module.User(name="alice", password=None))
        session.commit()
        assert [
            row.name
            for row in session.query(real_orm_module.GameMode).order_by(
                real_orm_module.GameMode.game_mode_id
            )
        ] == ["Singles", "Teams"]
        assert [
            row.name
            for row in session.query(real_orm_module.GameState).order_by(
                real_orm_module.GameState.game_state_id
            )
        ] == ["Starting", "StartingFull", "InProgress", "Completed"]
        assert [
            row.name
            for row in session.query(real_orm_module.RatingType).order_by(
                real_orm_module.RatingType.rating_type_id
            )
        ] == ["Singles2", "Singles3", "Singles4", "Teams"]
        assert session.query(real_orm_module.User).filter_by(name="Alice").one().user_id
        assert session.query(real_orm_module.User).filter_by(name="alice").one().user_id
    finally:
        session.close()

    with mysql_engine.begin() as connection:
        command.downgrade(_alembic_config(connection), "base")
    with mysql_engine.begin() as connection:
        connection.execute(sqlalchemy.text("drop table if exists alembic_version"))
    assert not _table_names(mysql_engine)


def _column_contract(inspector, table_name):
    primary_key_columns = set(inspector.get_pk_constraint(table_name)["constrained_columns"])
    return [
        (column["name"], column["nullable"], column["name"] in primary_key_columns)
        for column in inspector.get_columns(table_name)
    ]


def _unique_contract(inspector):
    contract = {}
    for table_name in _app_table_names(inspector.bind):
        unique_columns = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(table_name)
        }
        if unique_columns:
            contract[table_name] = unique_columns
    return contract


def _foreign_key_contract(inspector):
    contract = {}
    for table_name in _app_table_names(inspector.bind):
        foreign_keys = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspector.get_foreign_keys(table_name)
        }
        if foreign_keys:
            contract[table_name] = foreign_keys
    return contract


def _table_collation_contract(inspector):
    return {
        table_name: inspector.get_table_options(table_name)["mysql_collate"]
        for table_name in _app_table_names(inspector.bind)
    }


def test_initialize_database_seeds_lookup_rows_in_mysql(
    mysql_engine,
    real_orm_module,
    empty_mysql_schema,
    monkeypatch,
):
    sys.modules.pop("initialize_database", None)
    initialize_database = importlib.import_module("initialize_database")
    monkeypatch.setattr(initialize_database.orm, "engine", mysql_engine)
    initialize_database.orm.Session.configure(bind=mysql_engine)
    reset_calls = []

    def reset_schema(command):
        reset_calls.append(command)
        real_orm_module.Base.metadata.drop_all(mysql_engine)
        return 0

    monkeypatch.setattr(initialize_database.subprocess, "call", reset_schema)

    try:
        initialize_database.main()
        initialize_database.main()

        session = make_mysql_session(mysql_engine)
        try:
            assert [
                row.name
                for row in session.query(real_orm_module.GameMode).order_by(
                    real_orm_module.GameMode.game_mode_id
                )
            ] == ["Singles", "Teams"]
            assert [
                row.name
                for row in session.query(real_orm_module.GameState).order_by(
                    real_orm_module.GameState.game_state_id
                )
            ] == ["Starting", "StartingFull", "InProgress", "Completed"]
            assert [
                row.name
                for row in session.query(real_orm_module.RatingType).order_by(
                    real_orm_module.RatingType.rating_type_id
                )
            ] == ["Singles2", "Singles3", "Singles4", "Teams"]
            assert len(reset_calls) == 2
        finally:
            session.close()
    finally:
        sys.modules.pop("initialize_database", None)


def test_session_scope_commits_and_rolls_back_against_mysql(
    mysql_engine,
    real_orm_module,
    empty_mysql_schema,
):
    real_orm_module.Base.metadata.create_all(mysql_engine)
    real_orm_module.Session.configure(bind=mysql_engine)

    with real_orm_module.session_scope() as session:
        session.add(real_orm_module.User(name="committed", password="secret"))

    with (
        pytest.raises(RuntimeError, match="rollback"),
        real_orm_module.session_scope() as session,
    ):
        session.add(real_orm_module.User(name="rolled-back", password="secret"))
        raise RuntimeError("rollback")

    session = make_mysql_session(mysql_engine)
    try:
        names = [
            row.name
            for row in session.query(real_orm_module.User).order_by(real_orm_module.User.name)
        ]
    finally:
        session.close()

    assert names == ["committed"]


def test_auth_password_and_login_rules_against_mysql(
    mysql_engine,
    real_orm_module,
    real_auth_module,
    empty_mysql_schema,
):
    password_hash = "a" * 64
    replacement_hash = "b" * 64
    real_orm_module.Base.metadata.create_all(mysql_engine)
    session = make_mysql_session(mysql_engine)
    try:
        assert (
            real_auth_module.set_password(
                session,
                version="VERSION",
                username="alice",
                password=password_hash,
            )
            is None
        )
        session.commit()

        alice = session.query(real_orm_module.User).filter_by(name="alice").one()
        assert alice.password == password_hash
        assert (
            real_auth_module.set_password(
                session,
                version="VERSION",
                username="alice",
                password=replacement_hash,
            )
            is real_auth_module.enums.Errors.ExistingPassword
        )

        success = real_auth_module.check_login(
            session,
            version="VERSION",
            username="alice",
            password=password_hash,
        )
        assert success.error is None
        assert success.replace_existing_user is True

        wrong_password = real_auth_module.check_login(
            session,
            version="VERSION",
            username="alice",
            password=replacement_hash,
        )
        assert wrong_password.error is real_auth_module.enums.Errors.IncorrectPassword

        missing_user = real_auth_module.check_login(
            session,
            version="VERSION",
            username="missing",
            password="",
        )
        assert missing_user.error is None
        assert missing_user.replace_existing_user is False

        missing_user_with_password = real_auth_module.check_login(
            session,
            version="VERSION",
            username="missing",
            password=password_hash,
        )
        assert missing_user_with_password.error is real_auth_module.enums.Errors.ProvidedPassword

        session.add(real_orm_module.User(name="bob", password=None))
        session.commit()
        assert (
            real_auth_module.set_password(
                session,
                version="VERSION",
                username="bob",
                password=replacement_hash,
            )
            is None
        )
        session.commit()
        bob = session.query(real_orm_module.User).filter_by(name="bob").one()
        assert bob.password == replacement_hash
    finally:
        session.close()


def test_mysql_enforces_runtime_unique_constraints(
    mysql_engine,
    real_orm_module,
    empty_mysql_schema,
):
    real_orm_module.Base.metadata.create_all(mysql_engine)
    session = make_mysql_session(mysql_engine)
    try:
        seed_lookup_rows(session, real_orm_module)
        session.add(real_orm_module.User(name="alice", password="secret"))
        session.commit()

        session.add(real_orm_module.User(name="alice", password="different"))
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            session.commit()
        session.rollback()

        lookup = real_orm_module.Lookup(session)
        with session.no_autoflush:
            first_game = lookup.get_game(12345, 7)
            first_game.game_state = lookup.get_game_state("Starting")
            first_game.game_mode = lookup.get_game_mode("Singles")
        session.commit()

        duplicate_game = real_orm_module.Game(
            log_time=12345,
            number=7,
            game_state=lookup.get_game_state("Starting"),
            game_mode=lookup.get_game_mode("Singles"),
        )
        session.add(duplicate_game)
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            session.commit()
    finally:
        session.close()


def test_lookup_helpers_create_reuse_and_query_rows_against_mysql(
    mysql_engine,
    real_orm_module,
    empty_mysql_schema,
):
    real_orm_module.Base.metadata.create_all(mysql_engine)
    session = make_mysql_session(mysql_engine)
    try:
        seed_lookup_rows(session, real_orm_module)
        lookup = real_orm_module.Lookup(session)

        with session.no_autoflush:
            game = lookup.get_game(20000, 3)
            game.game_state = lookup.get_game_state("Starting")
            game.game_mode = lookup.get_game_mode("Singles")
            player = lookup.get_game_player(game, 0)
            player.user = lookup.get_user("alice")
            key_value = lookup.get_key_value("cron last offset")
            key_value.value = "42"
        session.commit()

        lookup = real_orm_module.Lookup(session)
        same_game = lookup.get_game(20000, 3)
        same_player = lookup.get_game_player(same_game, 0)
        same_user = lookup.get_user("alice")
        same_key_value = lookup.get_key_value("cron last offset")

        assert same_game.game_id == game.game_id
        assert same_player.game_player_id == player.game_player_id
        assert same_player.user_id == same_user.user_id
        assert same_key_value.value == "42"
        assert lookup.get_game_mode("Singles").name == "Singles"
        assert lookup.get_game_state("Starting").name == "Starting"
        assert lookup.get_rating_type("Singles2").name == "Singles2"
    finally:
        session.close()


def test_logs2db_persists_completed_game_ratings_and_records_against_mysql(
    mysql_engine,
    real_orm_module,
    real_cron_module,
    empty_mysql_schema,
    monkeypatch,
):
    real_orm_module.Base.metadata.create_all(mysql_engine)
    session = make_mysql_session(mysql_engine)
    try:
        seed_lookup_rows(session, real_orm_module)
        lookup = real_orm_module.Lookup(session)
        logs2db = real_cron_module.Logs2DB(session, lookup)
        log = io.StringIO(
            '{"_":"game","game-id":1,"state":"Starting","mode":"Singles","begin":1000}\n'
            '{"_":"game-player","game-id":1,"player-id":0,"username":"alice"}\n'
            '{"_":"game-player","game-id":1,"player-id":1,"username":"bob"}\n'
            '{"_":"game","game-id":1,"state":"Completed","end":1100,"score":[90,70]}\n'
        )

        offset, completed_game_users = logs2db.process_logs(log, log_time=555)
        session.commit()

        assert offset == len(log.getvalue())
        assert {user.name for user in completed_game_users} == {"alice", "bob"}

        persisted_game = session.query(real_orm_module.Game).filter_by(log_time=555, number=1).one()
        assert persisted_game.begin_time == 1000
        assert persisted_game.end_time == 1100
        assert persisted_game.game_state.name == "Completed"
        assert persisted_game.game_mode.name == "Singles"

        players = (
            session.query(real_orm_module.GamePlayer)
            .join(real_orm_module.User)
            .filter(real_orm_module.GamePlayer.game_id == persisted_game.game_id)
            .order_by(real_orm_module.GamePlayer.player_index)
            .all()
        )
        assert [(player.user.name, player.score) for player in players] == [
            ("alice", 90),
            ("bob", 70),
        ]

        ratings = (
            session.query(real_orm_module.Rating)
            .join(real_orm_module.User)
            .join(real_orm_module.RatingType)
            .order_by(real_orm_module.User.name, real_orm_module.Rating.time)
            .all()
        )
        assert [(rating.user.name, rating.rating_type.name, rating.time) for rating in ratings] == [
            ("alice", "Singles2", 1000),
            ("alice", "Singles2", 1100),
            ("bob", "Singles2", 1000),
            ("bob", "Singles2", 1100),
        ]
        assert all(rating.mu is not None and rating.sigma is not None for rating in ratings)

        records = {
            record.user.name: ujson.decode(record.encoded)
            for record in session.query(real_orm_module.Record).all()
        }
        assert records == {
            "alice": [[1, 0], [0, 0, 0], [0, 0, 0, 0], [0, 0]],
            "bob": [[0, 1], [0, 0, 0], [0, 0, 0, 0], [0, 0]],
        }

        written = {}
        statsgen = real_cron_module.StatsGen(session, "unused")
        monkeypatch.setattr(real_cron_module.time, "time", lambda: 1200)
        monkeypatch.setattr(
            statsgen,
            "write_file",
            lambda name, contents: written.update({name: contents}),
        )

        statsgen.output_ratings()

        assert written["ratings"].keys() == {"Singles2"}
        assert [rating[0] for rating in written["ratings"]["Singles2"]] == ["alice", "bob"]
    finally:
        session.close()
