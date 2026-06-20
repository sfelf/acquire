import time
import uuid

import pytest
import sqlalchemy


pytestmark = pytest.mark.mysql


def test_mysql_database_accepts_writes_and_reads(mysql_test_url):
    table_name = "acquire_smoke_%s" % uuid.uuid4().hex
    engine = sqlalchemy.create_engine(mysql_test_url)
    table_created = False
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                with engine.begin() as connection:
                    connection.execute(
                        sqlalchemy.text(
                            "create table `%s` (id int primary key, name varchar(32) not null)"
                            % table_name
                        )
                    )
                    table_created = True
                    connection.execute(
                        sqlalchemy.text(
                            "insert into `%s` (id, name) values (1, 'alice')"
                            % table_name
                        )
                    )
                    value = connection.execute(
                        sqlalchemy.text("select name from `%s` where id = 1" % table_name)
                    ).scalar()
                break
            except sqlalchemy.exc.DBAPIError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        assert value == "alice"
    finally:
        try:
            if table_created:
                with engine.begin() as connection:
                    connection.execute(
                        sqlalchemy.text("drop table if exists `%s`" % table_name)
                    )
        finally:
            engine.dispose()
