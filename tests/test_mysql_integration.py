import importlib
import sys
import time

import pytest
import sqlalchemy
from sqlalchemy.orm import sessionmaker


pytestmark = pytest.mark.mysql


@pytest.fixture
def real_orm_module():
    sys.modules.pop("orm", None)
    try:
        yield importlib.import_module("orm")
    finally:
        sys.modules.pop("orm", None)


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
    real_orm_module.Base.metadata.drop_all(mysql_engine)
    yield
    real_orm_module.Base.metadata.drop_all(mysql_engine)


def _table_names(mysql_engine):
    return set(sqlalchemy.inspect(mysql_engine).get_table_names())


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
        tuple(sorted(index["column_names"]))
        for index in inspector.get_indexes("rating")
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

        Session = sessionmaker(bind=mysql_engine)
        session = Session()
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

    with pytest.raises(RuntimeError, match="rollback"):
        with real_orm_module.session_scope() as session:
            session.add(real_orm_module.User(name="rolled-back", password="secret"))
            raise RuntimeError("rollback")

    Session = sessionmaker(bind=mysql_engine)
    session = Session()
    try:
        names = [
            row.name
            for row in session.query(real_orm_module.User).order_by(
                real_orm_module.User.name
            )
        ]
    finally:
        session.close()

    assert names == ["committed"]
