import importlib
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.postgres
REPO_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def real_orm_module():
    sys.modules.pop("acquire.orm", None)
    try:
        yield importlib.import_module("acquire.orm")
    finally:
        sys.modules.pop("acquire.orm", None)


@pytest.fixture
def postgres_engine(postgres_test_url):
    engine = sqlalchemy.create_engine(postgres_test_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def empty_postgres_schema(postgres_engine):
    drop_postgres_schema(postgres_engine)
    yield
    drop_postgres_schema(postgres_engine)


def drop_postgres_schema(postgres_engine):
    with postgres_engine.begin() as connection:
        inspector = sqlalchemy.inspect(connection)
        for table_name in reversed(inspector.get_table_names()):
            connection.execute(
                sqlalchemy.text(f'drop table if exists "{table_name}" cascade')
            )


def _alembic_config(connection):
    config = Config(str(REPO_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _table_names(engine):
    return set(sqlalchemy.inspect(engine).get_table_names())


def _app_table_names(engine):
    return _table_names(engine) - {"alembic_version"}


def _check_constraint_names(inspector, table_name):
    return {
        constraint["name"]
        for constraint in inspector.get_check_constraints(table_name)
    }


def test_postgres_database_accepts_writes_and_reads(postgres_engine):
    table_name = f"pytest_postgres_smoke_{uuid.uuid4().hex}"
    table_created = False
    try:
        with postgres_engine.begin() as connection:
            connection.execute(
                sqlalchemy.text(
                    f'create table "{table_name}" (id integer primary key, name text not null)'
                )
            )
            table_created = True
            connection.execute(
                sqlalchemy.text(f'insert into "{table_name}" (id, name) values (1, :name)'),
                {"name": "postgres-smoke"},
            )
            result = connection.execute(
                sqlalchemy.text(f'select name from "{table_name}" where id = 1')
            )
            assert result.scalar_one() == "postgres-smoke"
    finally:
        if table_created:
            with postgres_engine.begin() as connection:
                connection.execute(sqlalchemy.text(f'drop table if exists "{table_name}"'))


def test_orm_metadata_creates_expected_tables_against_postgres(
    postgres_engine,
    real_orm_module,
    empty_postgres_schema,
):
    real_orm_module.Base.metadata.create_all(postgres_engine)

    assert _table_names(postgres_engine) == {
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

    inspector = sqlalchemy.inspect(postgres_engine)
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


def test_alembic_baseline_runs_against_postgres(
    postgres_engine,
    real_orm_module,
    empty_postgres_schema,
):
    with postgres_engine.begin() as connection:
        command.upgrade(_alembic_config(connection), "head")

    assert _app_table_names(postgres_engine) == {
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
    with postgres_engine.connect() as connection:
        version = connection.execute(sqlalchemy.text("select version_num from alembic_version"))
        assert version.scalar_one() == "20260622_0001"

    session = sessionmaker(bind=postgres_engine, autoflush=False)()
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
        session.add(real_orm_module.User(name="Alice", password=None))
        session.add(real_orm_module.User(name="alice", password=None))
        session.commit()
        assert session.query(real_orm_module.User).filter_by(name="Alice").one().user_id
        assert session.query(real_orm_module.User).filter_by(name="alice").one().user_id
    finally:
        session.close()

    with postgres_engine.begin() as connection:
        command.downgrade(_alembic_config(connection), "base")
    with postgres_engine.begin() as connection:
        connection.execute(sqlalchemy.text("drop table if exists alembic_version"))
    assert not _table_names(postgres_engine)


def test_alembic_baseline_preserves_mysql_numeric_contract_against_postgres(
    postgres_engine,
    empty_postgres_schema,
):
    with postgres_engine.begin() as connection:
        command.upgrade(_alembic_config(connection), "head")

    inspector = sqlalchemy.inspect(postgres_engine)
    assert "ck_game_log_time_unsigned" in _check_constraint_names(inspector, "game")
    assert "ck_game_mode_game_mode_id_unsigned" in _check_constraint_names(
        inspector, "game_mode"
    )
    assert "ck_game_player_score_unsigned" in _check_constraint_names(
        inspector, "game_player"
    )

    rating_columns = {
        column["name"]: column["type"]
        for column in inspector.get_columns("rating")
    }
    assert rating_columns["mu"].__class__.__name__ == "REAL"
    assert rating_columns["sigma"].__class__.__name__ == "REAL"

    with postgres_engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                'insert into "user" (user_id, name, password) values (:id, :name, null)'
            ),
            {"id": 2_147_483_648, "name": "above-signed-int"},
        )

    with (
        pytest.raises(sqlalchemy.exc.IntegrityError),
        postgres_engine.begin() as connection,
    ):
        connection.execute(
            sqlalchemy.text(
                'insert into "user" (user_id, name, password) values (-1, :name, null)'
            ),
            {"name": "negative-id"},
        )

    with (
        pytest.raises(sqlalchemy.exc.IntegrityError),
        postgres_engine.begin() as connection,
    ):
        connection.execute(
            sqlalchemy.text(
                'insert into game_mode (game_mode_id, name) values (256, :name)'
            ),
            {"name": "TooLarge"},
        )
