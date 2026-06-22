import uuid

import pytest
import sqlalchemy

pytestmark = pytest.mark.postgres


def test_postgres_database_accepts_writes_and_reads(postgres_test_url):
    engine = sqlalchemy.create_engine(postgres_test_url)
    table_name = f"pytest_postgres_smoke_{uuid.uuid4().hex}"
    table_created = False
    try:
        with engine.begin() as connection:
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
            with engine.begin() as connection:
                connection.execute(sqlalchemy.text(f'drop table if exists "{table_name}"'))
        engine.dispose()
