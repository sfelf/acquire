import time
import uuid

import pytest
import sqlalchemy

pytestmark = pytest.mark.mysql


def test_mysql_database_accepts_writes_and_reads(mysql_test_url):
    table_name = f"acquire_smoke_{uuid.uuid4().hex}"
    engine = sqlalchemy.create_engine(mysql_test_url)
    table_created = False
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                with engine.begin() as connection:
                    connection.execute(
                        sqlalchemy.text(
                            f"create table `{table_name}` "
                            "(id int primary key, name varchar(32) not null)"
                        )
                    )
                    table_created = True
                    connection.execute(
                        sqlalchemy.text(
                            f"insert into `{table_name}` (id, name) values (1, 'alice')"
                        )
                    )
                    value = connection.execute(
                        sqlalchemy.text(f"select name from `{table_name}` where id = 1")
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
                    connection.execute(sqlalchemy.text(f"drop table if exists `{table_name}`"))
        finally:
            engine.dispose()
