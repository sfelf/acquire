import importlib
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config
from conftest import _cleanup_docker_compose, _get_available_local_port, _run_docker_compose

pytestmark = [pytest.mark.mysql, pytest.mark.postgres]
REPO_DIR = Path(__file__).resolve().parents[1]
FALLBACK_POSTGRES_REHEARSAL_PORT = "35433"


@pytest.fixture
def real_orm_module():
    sys.modules.pop("orm", None)
    try:
        yield importlib.import_module("orm")
    finally:
        sys.modules.pop("orm", None)


@pytest.fixture
def import_module(real_orm_module):
    sys.modules.pop("import_mysql_to_postgres", None)
    try:
        yield importlib.import_module("import_mysql_to_postgres")
    finally:
        sys.modules.pop("import_mysql_to_postgres", None)


@pytest.fixture
def mysql_postgres_rehearsal_urls(pytestconfig):
    configured_mysql_url = os.environ.get("ACQUIRE_MYSQL_TEST_URL")
    configured_postgres_url = os.environ.get("ACQUIRE_POSTGRES_TEST_URL")
    if configured_mysql_url and configured_postgres_url:
        yield configured_mysql_url, configured_postgres_url
        return
    if configured_mysql_url or configured_postgres_url:
        pytest.skip("set both ACQUIRE_MYSQL_TEST_URL and ACQUIRE_POSTGRES_TEST_URL")
    if (
        "mysql" not in pytestconfig.option.markexpr
        and "postgres" not in pytestconfig.option.markexpr
    ):
        pytest.skip("mysql or postgres marker was not selected")

    project_name = f"acquire-pytest-import-{os.getpid()}"
    mysql_port = _get_available_local_port()
    postgres_port = _distinct_postgres_port(mysql_port, _get_available_local_port())
    compose_env = {
        "ACQUIRE_MYSQL_TEST_PORT": mysql_port,
        "ACQUIRE_POSTGRES_TEST_PORT": postgres_port,
        "MYSQL_DATABASE": os.environ.get("MYSQL_DATABASE", "acquire"),
        "MYSQL_USER": os.environ.get("MYSQL_USER", "acquire"),
        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "acquire"),
        "POSTGRES_DB": os.environ.get("POSTGRES_DB", "acquire"),
        "POSTGRES_USER": os.environ.get("POSTGRES_USER", "acquire"),
        "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD", "acquire"),
    }
    previous_env = {key: os.environ.get(key) for key in compose_env}
    os.environ.update(compose_env)
    try:
        _run_docker_compose(
            project_name,
            "up",
            "-d",
            "mysql",
            "postgres",
            include_test_override=True,
            profiles=("mysql",),
        )
        mysql_url = "mysql+mysqlconnector://{}:{}@127.0.0.1:{}/{}".format(
            quote(compose_env["MYSQL_USER"], safe=""),
            quote(compose_env["MYSQL_PASSWORD"], safe=""),
            mysql_port,
            compose_env["MYSQL_DATABASE"],
        )
        postgres_url = "postgresql+psycopg://{}:{}@127.0.0.1:{}/{}".format(
            quote(compose_env["POSTGRES_USER"], safe=""),
            quote(compose_env["POSTGRES_PASSWORD"], safe=""),
            postgres_port,
            compose_env["POSTGRES_DB"],
        )
        _wait_for_database(mysql_url)
        _wait_for_database(postgres_url)
        yield mysql_url, postgres_url
    finally:
        _cleanup_docker_compose(
            project_name,
            "down",
            "--volumes",
            include_test_override=True,
            profiles=("mysql",),
        )
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _distinct_postgres_port(mysql_port, postgres_port):
    if postgres_port != mysql_port:
        return postgres_port
    return FALLBACK_POSTGRES_REHEARSAL_PORT


def _wait_for_database(database_url):
    engine = sqlalchemy.create_engine(database_url)
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                with engine.connect() as connection:
                    connection.execute(sqlalchemy.text("select 1"))
                return
            except sqlalchemy.exc.DBAPIError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
    finally:
        engine.dispose()


def _alembic_config(connection):
    config = Config(str(REPO_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _reset_database(engine, orm):
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            inspector = sqlalchemy.inspect(connection)
            for table_name in reversed(inspector.get_table_names()):
                connection.execute(sqlalchemy.text(f'drop table if exists "{table_name}" cascade'))
    else:
        orm.Base.metadata.drop_all(engine)
        with engine.begin() as connection:
            connection.execute(sqlalchemy.text("drop table if exists alembic_version"))


def _upgrade_database(engine):
    with engine.begin() as connection:
        command.upgrade(_alembic_config(connection), "head")


def _lookup_id(connection, table, id_column, name):
    return connection.execute(
        sqlalchemy.select(table.c[id_column]).where(table.c.name == name)
    ).scalar_one()


def _seed_mysql_source(engine, orm):
    tables = orm.Base.metadata.tables
    with engine.begin() as connection:
        game_mode_id = _lookup_id(connection, tables["game_mode"], "game_mode_id", "Singles")
        game_state_id = _lookup_id(connection, tables["game_state"], "game_state_id", "Completed")
        rating_type_id = _lookup_id(connection, tables["rating_type"], "rating_type_id", "Singles2")
        connection.execute(
            tables["user"].insert(),
            [
                {"user_id": 100, "name": "Alice", "password": None},
                {"user_id": 101, "name": "Bob", "password": "b" * 64},
            ],
        )
        connection.execute(
            tables["game"].insert(),
            {
                "game_id": 200,
                "log_time": 12345,
                "number": 7,
                "begin_time": 12346,
                "end_time": 12399,
                "game_state_id": game_state_id,
                "game_mode_id": game_mode_id,
            },
        )
        connection.execute(
            tables["game_player"].insert(),
            [
                {
                    "game_player_id": 300,
                    "game_id": 200,
                    "player_index": 0,
                    "user_id": 100,
                    "score": 820,
                },
                {
                    "game_player_id": 301,
                    "game_id": 200,
                    "player_index": 1,
                    "user_id": 101,
                    "score": 610,
                },
            ],
        )
        connection.execute(
            tables["key_value"].insert(),
            {"key_value_id": 20, "key": "cron last offset", "value": "42"},
        )
        connection.execute(
            tables["rating"].insert(),
            [
                {
                    "rating_id": 400,
                    "user_id": 100,
                    "rating_type_id": rating_type_id,
                    "time": 12400,
                    "mu": 25.0,
                    "sigma": 8.333,
                },
                {
                    "rating_id": 401,
                    "user_id": 101,
                    "rating_type_id": rating_type_id,
                    "time": 12400,
                    "mu": 24.5,
                    "sigma": 8.1,
                },
            ],
        )
        connection.execute(
            tables["record"].insert(),
            [
                {"user_id": 100, "encoded": '{"wins": 1}'},
                {"user_id": 101, "encoded": '{"wins": 0}'},
            ],
        )


def _table_rows(engine, orm, table_name):
    table = orm.Base.metadata.tables[table_name]
    primary_key_columns = list(table.primary_key.columns)
    statement = sqlalchemy.select(table).order_by(*primary_key_columns)
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(statement)]


def test_import_rehearsal_copies_mysql_rows_into_postgres(
    mysql_postgres_rehearsal_urls,
    real_orm_module,
    import_module,
):
    mysql_url, postgres_url = mysql_postgres_rehearsal_urls
    mysql_engine = sqlalchemy.create_engine(mysql_url)
    postgres_engine = sqlalchemy.create_engine(postgres_url)
    try:
        _reset_database(mysql_engine, real_orm_module)
        _reset_database(postgres_engine, real_orm_module)
        _upgrade_database(mysql_engine)
        _upgrade_database(postgres_engine)
        _seed_mysql_source(mysql_engine, real_orm_module)

        report = import_module.import_database(mysql_url, postgres_url)

        assert report.total_rows == 20
        assert [
            (table.table_name, table.source_count, table.target_count)
            for table in report.tables
        ] == [
            ("game_mode", 2, 2),
            ("game_state", 4, 4),
            ("rating_type", 4, 4),
            ("user", 2, 2),
            ("game", 1, 1),
            ("game_player", 2, 2),
            ("key_value", 1, 1),
            ("rating", 2, 2),
            ("record", 2, 2),
        ]
        assert _table_rows(postgres_engine, real_orm_module, "user") == _table_rows(
            mysql_engine,
            real_orm_module,
            "user",
        )
        assert _table_rows(postgres_engine, real_orm_module, "game") == _table_rows(
            mysql_engine,
            real_orm_module,
            "game",
        )
        assert _table_rows(postgres_engine, real_orm_module, "game_player") == _table_rows(
            mysql_engine,
            real_orm_module,
            "game_player",
        )
        assert _table_rows(postgres_engine, real_orm_module, "key_value") == _table_rows(
            mysql_engine,
            real_orm_module,
            "key_value",
        )
        assert _table_rows(postgres_engine, real_orm_module, "rating") == _table_rows(
            mysql_engine,
            real_orm_module,
            "rating",
        )
        assert _table_rows(postgres_engine, real_orm_module, "record") == _table_rows(
            mysql_engine,
            real_orm_module,
            "record",
        )

        with postgres_engine.begin() as connection:
            inserted_id = connection.execute(
                real_orm_module.User.__table__.insert()
                .values(name="Charlie", password=None)
                .returning(real_orm_module.User.user_id)
            ).scalar_one()
        assert inserted_id > 101
    finally:
        mysql_engine.dispose()
        postgres_engine.dispose()
