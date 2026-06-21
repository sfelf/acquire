"""Initialize the MySQL schema and seed lookup tables for local development.

This module is part of the legacy Python runtime and replay tooling.
"""

import os
import subprocess

import orm


def main():
    """Run the module command-line entry point."""
    mysql_database = os.environ.get("MYSQL_DATABASE", "acquire")
    mysql_root_password = os.environ.get("MYSQL_ROOT_PASSWORD", "root")
    mysql_socket = os.environ.get("MYSQL_SOCKET", "/var/run/mysqld/mysqld.sock")
    escaped_mysql_database = mysql_database.replace("`", "``")
    reset_schema_sql = (
        f"drop schema if exists `{escaped_mysql_database}`; "
        f"create schema `{escaped_mysql_database}` "
        "default character set utf8mb4 collate utf8mb4_bin;"
    )

    subprocess.call(
        [
            "mysql",
            "--socket",
            mysql_socket,
            "-u",
            "root",
            "-p" + mysql_root_password,
            "-e",
            reset_schema_sql,
        ]
    )

    orm.Base.metadata.create_all(orm.engine)

    with orm.session_scope() as session:
        session.add(orm.GameMode(name="Singles"))
        session.add(orm.GameMode(name="Teams"))

        session.add(orm.GameState(name="Starting"))
        session.add(orm.GameState(name="StartingFull"))
        session.add(orm.GameState(name="InProgress"))
        session.add(orm.GameState(name="Completed"))

        session.add(orm.RatingType(name="Singles2"))
        session.add(orm.RatingType(name="Singles3"))
        session.add(orm.RatingType(name="Singles4"))
        session.add(orm.RatingType(name="Teams"))


if __name__ == "__main__":
    main()
