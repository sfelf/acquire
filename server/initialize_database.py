import orm
import os
import subprocess


def main():
    mysql_database = os.environ.get("MYSQL_DATABASE", "acquire")
    mysql_root_password = os.environ.get("MYSQL_ROOT_PASSWORD", "root")
    mysql_socket = os.environ.get("MYSQL_SOCKET", "/var/run/mysqld/mysqld.sock")
    escaped_mysql_database = mysql_database.replace("`", "``")

    subprocess.call(
        [
            "mysql",
            "--socket",
            mysql_socket,
            "-u",
            "root",
            "-p" + mysql_root_password,
            "-e",
            "drop schema if exists `%s`; create schema `%s` default character set utf8mb4 collate utf8mb4_bin;"
            % (escaped_mysql_database, escaped_mysql_database),
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
