import os
import uuid

import pytest
import sqlalchemy


pytestmark = pytest.mark.mysql


def test_mysql_database_accepts_writes_and_reads():
    database_url = os.environ.get("ACQUIRE_MYSQL_TEST_URL")
    if not database_url:
        pytest.skip("ACQUIRE_MYSQL_TEST_URL is required for mysql smoke tests")

    table_name = "acquire_smoke_%s" % uuid.uuid4().hex
    engine = sqlalchemy.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sqlalchemy.text(
                    "create table `%s` (id int primary key, name varchar(32) not null)"
                    % table_name
                )
            )
            connection.execute(
                sqlalchemy.text("insert into `%s` (id, name) values (1, 'alice')" % table_name)
            )
            value = connection.execute(
                sqlalchemy.text("select name from `%s` where id = 1" % table_name)
            ).scalar()
        assert value == "alice"
    finally:
        with engine.begin() as connection:
            connection.execute(sqlalchemy.text("drop table if exists `%s`" % table_name))
        engine.dispose()
