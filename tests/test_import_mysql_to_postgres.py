import importlib
import json

import pytest
import sqlalchemy
from sqlalchemy.dialects import mysql, postgresql

pytestmark = pytest.mark.unit

EXPECTED_LEGACY_SOURCE_SCHEMA = {
    "game_mode": (
        ("game_mode_id", "TINYINT UNSIGNED", False, True),
        ("name", "VARCHAR(8)", False, False),
    ),
    "game_state": (
        ("game_state_id", "TINYINT UNSIGNED", False, True),
        ("name", "VARCHAR(16)", False, False),
    ),
    "rating_type": (
        ("rating_type_id", "TINYINT UNSIGNED", False, True),
        ("name", "VARCHAR(8)", False, False),
    ),
    "user": (
        ("user_id", "INTEGER UNSIGNED", False, True),
        ("name", "VARCHAR(32)", False, False),
        ("password", "VARCHAR(64)", True, False),
    ),
    "game": (
        ("game_id", "INTEGER UNSIGNED", False, True),
        ("log_time", "INTEGER UNSIGNED", False, False),
        ("number", "INTEGER UNSIGNED", False, False),
        ("begin_time", "INTEGER UNSIGNED", True, False),
        ("end_time", "INTEGER UNSIGNED", True, False),
        ("game_state_id", "TINYINT UNSIGNED", False, False),
        ("game_mode_id", "TINYINT UNSIGNED", False, False),
    ),
    "game_player": (
        ("game_player_id", "INTEGER UNSIGNED", False, True),
        ("game_id", "INTEGER UNSIGNED", False, False),
        ("player_index", "TINYINT UNSIGNED", False, False),
        ("user_id", "INTEGER UNSIGNED", False, False),
        ("score", "SMALLINT UNSIGNED", True, False),
    ),
    "key_value": (
        ("key_value_id", "TINYINT UNSIGNED", False, True),
        ("key", "VARCHAR(32)", False, False),
        ("value", "TEXT", False, False),
    ),
    "rating": (
        ("rating_id", "INTEGER UNSIGNED", False, True),
        ("user_id", "INTEGER UNSIGNED", False, False),
        ("rating_type_id", "TINYINT UNSIGNED", False, False),
        ("time", "INTEGER UNSIGNED", False, False),
        ("mu", "FLOAT", False, False),
        ("sigma", "FLOAT", False, False),
    ),
    "record": (
        ("user_id", "INTEGER UNSIGNED", False, True),
        ("encoded", "VARCHAR(255)", False, False),
    ),
}

EXPECTED_CURRENT_TARGET_SCHEMA = {
    "game_mode": (
        ("game_mode_id", "SMALLINT", False, True),
        ("name", "VARCHAR(8)", False, False),
    ),
    "game_state": (
        ("game_state_id", "SMALLINT", False, True),
        ("name", "VARCHAR(16)", False, False),
    ),
    "rating_type": (
        ("rating_type_id", "SMALLINT", False, True),
        ("name", "VARCHAR(8)", False, False),
    ),
    "user": (
        ("user_id", "BIGINT", False, True),
        ("name", "VARCHAR(32)", False, False),
        ("password", "VARCHAR(64)", True, False),
    ),
    "game": (
        ("game_id", "BIGINT", False, True),
        ("log_time", "BIGINT", False, False),
        ("number", "BIGINT", False, False),
        ("begin_time", "BIGINT", True, False),
        ("end_time", "BIGINT", True, False),
        ("game_state_id", "SMALLINT", False, False),
        ("game_mode_id", "SMALLINT", False, False),
    ),
    "game_player": (
        ("game_player_id", "BIGINT", False, True),
        ("game_id", "BIGINT", False, False),
        ("player_index", "SMALLINT", False, False),
        ("user_id", "BIGINT", False, False),
        ("score", "INTEGER", True, False),
    ),
    "key_value": (
        ("key_value_id", "SMALLINT", False, True),
        ("key", "VARCHAR(32)", False, False),
        ("value", "TEXT", False, False),
    ),
    "rating": (
        ("rating_id", "BIGINT", False, True),
        ("user_id", "BIGINT", False, False),
        ("rating_type_id", "SMALLINT", False, False),
        ("time", "BIGINT", False, False),
        ("mu", "REAL", False, False),
        ("sigma", "REAL", False, False),
    ),
    "record": (
        ("user_id", "BIGINT", False, True),
        ("encoded", "VARCHAR(255)", False, False),
    ),
}


@pytest.fixture
def import_module():
    return importlib.import_module("acquire.migration.import_mysql_to_postgres")


@pytest.fixture
def schema_module():
    return importlib.import_module("acquire.migration.schema")


@pytest.fixture
def source_engine(schema_module):
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    schema_module.LEGACY_SOURCE_METADATA.create_all(engine)
    seed_source_database(engine, schema_module.LEGACY_SOURCE_TABLES)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def target_engine(schema_module):
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    schema_module.CURRENT_TARGET_METADATA.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def seed_source_database(engine, tables):
    with engine.begin() as connection:
        connection.execute(
            tables["game_mode"].insert(),
            [
                {"game_mode_id": 1, "name": "Singles"},
                {"game_mode_id": 2, "name": "Teams"},
            ],
        )
        connection.execute(
            tables["game_state"].insert(),
            [
                {"game_state_id": 1, "name": "Starting"},
                {"game_state_id": 2, "name": "Completed"},
            ],
        )
        connection.execute(
            tables["rating_type"].insert(),
            [
                {"rating_type_id": 1, "name": "Singles2"},
                {"rating_type_id": 2, "name": "Teams"},
            ],
        )
        connection.execute(
            tables["user"].insert(),
            [
                {"user_id": 1, "name": "Alice", "password": None},
                {"user_id": 2, "name": "Bob", "password": "b" * 64},
            ],
        )
        connection.execute(
            tables["game"].insert(),
            [
                {
                    "game_id": 10,
                    "log_time": 12345,
                    "number": 7,
                    "begin_time": 12346,
                    "end_time": 12399,
                    "game_state_id": 2,
                    "game_mode_id": 1,
                }
            ],
        )
        connection.execute(
            tables["game_player"].insert(),
            [
                {
                    "game_player_id": 20,
                    "game_id": 10,
                    "player_index": 0,
                    "user_id": 1,
                    "score": 820,
                }
            ],
        )
        connection.execute(
            tables["key_value"].insert(),
            [{"key_value_id": 1, "key": "cron last offset", "value": "42"}],
        )
        connection.execute(
            tables["rating"].insert(),
            [
                {
                    "rating_id": 30,
                    "user_id": 1,
                    "rating_type_id": 1,
                    "time": 12400,
                    "mu": 25.0,
                    "sigma": 8.333,
                }
            ],
        )
        connection.execute(
            tables["record"].insert(),
            [{"user_id": 1, "encoded": '{"wins": 1}'}],
        )


def seed_matching_lookup_rows(engine, tables):
    with engine.begin() as connection:
        connection.execute(
            tables["game_mode"].insert(),
            [
                {"game_mode_id": 1, "name": "Singles"},
                {"game_mode_id": 2, "name": "Teams"},
            ],
        )
        connection.execute(
            tables["game_state"].insert(),
            [
                {"game_state_id": 1, "name": "Starting"},
                {"game_state_id": 2, "name": "Completed"},
            ],
        )
        connection.execute(
            tables["rating_type"].insert(),
            [
                {"rating_type_id": 1, "name": "Singles2"},
                {"rating_type_id": 2, "name": "Teams"},
            ],
        )


def table_rows(engine, tables, table_name):
    table = tables[table_name]
    primary_key_columns = list(table.primary_key.columns)
    statement = sqlalchemy.select(table).order_by(*primary_key_columns)
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(statement)]


def schema_contract(tables, dialect):
    return {
        table_name: tuple(
            (
                column.name,
                str(column.type.compile(dialect=dialect)),
                column.nullable,
                column.primary_key,
            )
            for column in table.columns
        )
        for table_name, table in tables.items()
    }


def test_migration_schemas_preserve_explicit_source_and_target_contracts(
    import_module,
    schema_module,
):
    assert tuple(import_module.TABLE_ORDER) == (
        "game_mode",
        "game_state",
        "rating_type",
        "user",
        "game",
        "game_player",
        "key_value",
        "rating",
        "record",
    )
    assert schema_contract(
        schema_module.LEGACY_SOURCE_TABLES,
        mysql.dialect(),
    ) == EXPECTED_LEGACY_SOURCE_SCHEMA
    assert schema_contract(
        schema_module.CURRENT_TARGET_TABLES,
        postgresql.dialect(),
    ) == EXPECTED_CURRENT_TARGET_SCHEMA
    assert schema_module.LEGACY_SOURCE_METADATA is not schema_module.CURRENT_TARGET_METADATA


def test_current_target_schema_matches_runtime_orm_contract(schema_module):
    orm_module = importlib.import_module("acquire.orm")

    assert schema_contract(
        schema_module.CURRENT_TARGET_TABLES,
        postgresql.dialect(),
    ) == schema_contract(
        dict(orm_module.Base.metadata.tables),
        postgresql.dialect(),
    )


def test_import_engines_copies_rows_into_migrated_postgres_shape(
    import_module,
    schema_module,
    source_engine,
    target_engine,
):
    seed_matching_lookup_rows(target_engine, schema_module.CURRENT_TARGET_TABLES)

    report = import_module.import_engines(source_engine, target_engine)

    assert report.dry_run is False
    assert report.total_rows == 13
    reported_counts = [
        (table.table_name, table.source_count, table.target_count)
        for table in report.tables
    ]
    assert reported_counts == [
        ("game_mode", 2, 2),
        ("game_state", 2, 2),
        ("rating_type", 2, 2),
        ("user", 2, 2),
        ("game", 1, 1),
        ("game_player", 1, 1),
        ("key_value", 1, 1),
        ("rating", 1, 1),
        ("record", 1, 1),
    ]
    assert table_rows(target_engine, schema_module.CURRENT_TARGET_TABLES, "user") == table_rows(
        source_engine, schema_module.LEGACY_SOURCE_TABLES, "user"
    )
    assert table_rows(
        target_engine,
        schema_module.CURRENT_TARGET_TABLES,
        "game_player",
    ) == table_rows(
        source_engine,
        schema_module.LEGACY_SOURCE_TABLES,
        "game_player",
    )
    assert table_rows(target_engine, schema_module.CURRENT_TARGET_TABLES, "record") == table_rows(
        source_engine, schema_module.LEGACY_SOURCE_TABLES, "record"
    )


def test_import_engines_rejects_non_empty_mutable_target_table(
    import_module,
    schema_module,
    source_engine,
    target_engine,
):
    target_tables = schema_module.CURRENT_TARGET_TABLES
    seed_matching_lookup_rows(target_engine, target_tables)
    with target_engine.begin() as connection:
        connection.execute(
            target_tables["user"].insert(),
            {"user_id": 99, "name": "Existing", "password": None},
        )

    with pytest.raises(
        import_module.TargetNotEmptyError,
        match="target table must be empty before import: user",
    ):
        import_module.import_engines(source_engine, target_engine)

    assert table_rows(target_engine, target_tables, "user") == [
        {"user_id": 99, "name": "Existing", "password": None}
    ]


def test_import_engines_rejects_mismatched_lookup_rows(
    import_module,
    schema_module,
    source_engine,
    target_engine,
):
    with target_engine.begin() as connection:
        connection.execute(
            schema_module.CURRENT_TARGET_TABLES["game_mode"].insert(),
            {"game_mode_id": 1, "name": "Different"},
        )

    with pytest.raises(
        import_module.ImportValidationError,
        match="target lookup table game_mode does not match source rows",
    ):
        import_module.import_engines(source_engine, target_engine)


def test_import_engines_rolls_back_rows_after_partial_insert_failure(
    import_module,
    schema_module,
    source_engine,
    target_engine,
):
    target_tables = schema_module.CURRENT_TARGET_TABLES
    seed_matching_lookup_rows(target_engine, target_tables)

    def fail_game_insert(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        if statement.startswith("INSERT INTO game "):
            raise RuntimeError("simulated game insert failure")

    sqlalchemy.event.listen(target_engine, "before_cursor_execute", fail_game_insert)

    with pytest.raises(RuntimeError, match="simulated game insert failure"):
        import_module.import_engines(source_engine, target_engine)

    assert table_rows(target_engine, target_tables, "user") == []
    assert table_rows(target_engine, target_tables, "game") == []
    assert len(table_rows(target_engine, target_tables, "game_mode")) == 2


def test_import_engines_rolls_back_target_count_mismatch(
    import_module,
    schema_module,
    source_engine,
    target_engine,
    monkeypatch,
):
    target_tables = schema_module.CURRENT_TARGET_TABLES
    seed_matching_lookup_rows(target_engine, target_tables)
    count_rows = import_module._count_rows

    def report_wrong_user_count(connection, table):
        count = count_rows(connection, table)
        if connection.engine is target_engine and table.name == "user":
            return count - 1
        return count

    monkeypatch.setattr(import_module, "_count_rows", report_wrong_user_count)

    with pytest.raises(
        import_module.ImportValidationError,
        match="user imported 1 rows; expected 2",
    ):
        import_module.import_engines(source_engine, target_engine)

    assert table_rows(target_engine, target_tables, "user") == []


def test_import_engines_dry_run_reports_counts_without_writing(
    import_module,
    schema_module,
    source_engine,
    target_engine,
):
    target_tables = schema_module.CURRENT_TARGET_TABLES
    seed_matching_lookup_rows(target_engine, target_tables)

    report = import_module.import_engines(source_engine, target_engine, dry_run=True)

    assert report.dry_run is True
    assert report.total_rows == 13
    assert table_rows(target_engine, target_tables, "user") == []
    assert table_rows(target_engine, target_tables, "game") == []


def test_import_engines_accepts_required_source_tables_with_rows(
    import_module,
    schema_module,
    source_engine,
    target_engine,
):
    seed_matching_lookup_rows(target_engine, schema_module.CURRENT_TARGET_TABLES)

    report = import_module.import_engines(
        source_engine,
        target_engine,
        dry_run=True,
        required_source_tables=["rating", "record"],
    )

    assert report.total_rows == 13


def test_import_engines_rejects_empty_required_source_table_before_writing(
    import_module,
    schema_module,
    source_engine,
    target_engine,
):
    with source_engine.begin() as connection:
        connection.execute(sqlalchemy.text("delete from rating"))
    target_tables = schema_module.CURRENT_TARGET_TABLES
    seed_matching_lookup_rows(target_engine, target_tables)

    with pytest.raises(
        import_module.ImportValidationError,
        match="rating: required source table has no rows",
    ):
        import_module.import_engines(
            source_engine,
            target_engine,
            required_source_tables=["rating"],
        )

    assert table_rows(target_engine, target_tables, "user") == []


def test_import_engines_rejects_unknown_required_source_table(
    import_module,
    source_engine,
    target_engine,
):
    with pytest.raises(
        import_module.ImportValidationError,
        match="missing_table: required source table is unknown",
    ):
        import_module.import_engines(
            source_engine,
            target_engine,
            required_source_tables=["missing_table"],
        )


@pytest.mark.parametrize("table_name", ["key_value", "record"])
def test_import_engines_rejects_missing_required_source_tables(
    import_module,
    schema_module,
    source_engine,
    target_engine,
    table_name,
):
    with source_engine.begin() as connection:
        connection.execute(sqlalchemy.text(f"drop table {table_name}"))
    seed_matching_lookup_rows(target_engine, schema_module.CURRENT_TARGET_TABLES)

    with pytest.raises(
        import_module.ImportValidationError,
        match=f"source database is missing required tables: {table_name}",
    ):
        import_module.import_engines(source_engine, target_engine)


def test_import_database_builds_engines_from_urls(import_module, schema_module, tmp_path):
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    source_engine = sqlalchemy.create_engine(source_url)
    target_engine = sqlalchemy.create_engine(target_url)
    try:
        schema_module.LEGACY_SOURCE_METADATA.create_all(source_engine)
        schema_module.CURRENT_TARGET_METADATA.create_all(target_engine)
        seed_source_database(source_engine, schema_module.LEGACY_SOURCE_TABLES)
        seed_matching_lookup_rows(target_engine, schema_module.CURRENT_TARGET_TABLES)
    finally:
        source_engine.dispose()
        target_engine.dispose()

    report = import_module.import_database(source_url, target_url)

    assert report.total_rows == 13
    verify_engine = sqlalchemy.create_engine(target_url)
    try:
        assert table_rows(verify_engine, schema_module.CURRENT_TARGET_TABLES, "user") == [
            {"user_id": 1, "name": "Alice", "password": None},
            {"user_id": 2, "name": "Bob", "password": "b" * 64},
        ]
    finally:
        verify_engine.dispose()


def test_main_prints_import_report(import_module, capsys, monkeypatch):
    report = import_module.ImportReport(
        dry_run=True,
        tables=(
            import_module.TableImportResult(
                table_name="user",
                source_count=2,
                target_count=0,
            ),
        ),
    )
    monkeypatch.setattr(
        import_module,
        "import_database",
        lambda source_url, target_url, *, dry_run, required_source_tables: report,
    )

    exit_code = import_module.main(
        [
            "--source-url",
            "mysql+mysqlconnector://source",
            "--target-url",
            "postgresql+psycopg://target",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "dry run covered 2 rows\nuser: source=2 target=0\n"


def test_write_report_json_records_sanitized_table_counts(import_module, tmp_path):
    report = import_module.ImportReport(
        dry_run=False,
        tables=(
            import_module.TableImportResult(
                table_name="user",
                source_count=2,
                target_count=2,
            ),
            import_module.TableImportResult(
                table_name="game",
                source_count=1,
                target_count=1,
            ),
        ),
    )
    report_path = tmp_path / "nested" / "import-report.json"

    import_module.write_report_json(report, report_path)

    payload = json.loads(report_path.read_text())
    assert payload == {
        "dry_run": False,
        "total_rows": 3,
        "tables": [
            {"source_count": 2, "table_name": "user", "target_count": 2},
            {"source_count": 1, "table_name": "game", "target_count": 1},
        ],
    }
    assert "mysql" not in report_path.read_text()
    assert "postgres" not in report_path.read_text()
    assert "://" not in report_path.read_text()


def test_main_writes_report_json_when_requested(import_module, capsys, monkeypatch, tmp_path):
    report = import_module.ImportReport(
        dry_run=True,
        tables=(
            import_module.TableImportResult(
                table_name="user",
                source_count=2,
                target_count=0,
            ),
        ),
    )
    monkeypatch.setattr(
        import_module,
        "import_database",
        lambda source_url, target_url, *, dry_run, required_source_tables: report,
    )
    report_path = tmp_path / "import-report.json"

    exit_code = import_module.main(
        [
            "--source-url",
            "mysql+mysqlconnector://user:password@source/acquire",
            "--target-url",
            "postgresql+psycopg://user:password@target/acquire",
            "--dry-run",
            "--report-json",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(report_path.read_text()) == {
        "dry_run": True,
        "total_rows": 2,
        "tables": [{"source_count": 2, "table_name": "user", "target_count": 0}],
    }
    assert capsys.readouterr().out == "dry run covered 2 rows\nuser: source=2 target=0\n"


def test_main_preflights_report_path_before_importing(
    import_module,
    monkeypatch,
    tmp_path,
):
    call_order = []
    report = import_module.ImportReport(
        dry_run=False,
        tables=(
            import_module.TableImportResult(
                table_name="user",
                source_count=2,
                target_count=2,
            ),
        ),
    )

    def record_preflight(path):
        call_order.append(("preflight", path.exists()))
        path.write_text("")

    def record_import(source_url, target_url, *, dry_run, required_source_tables):
        call_order.append(("import", dry_run, tuple(required_source_tables)))
        return report

    monkeypatch.setattr(import_module, "preflight_report_json_path", record_preflight)
    monkeypatch.setattr(import_module, "import_database", record_import)
    report_path = tmp_path / "import-report.json"

    exit_code = import_module.main(
        [
            "--source-url",
            "mysql+mysqlconnector://source",
            "--target-url",
            "postgresql+psycopg://target",
            "--report-json",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert call_order == [("preflight", False), ("import", False, ())]
    assert json.loads(report_path.read_text())["total_rows"] == 2


def test_main_passes_required_source_tables_to_import(import_module, monkeypatch):
    import_calls = []
    report = import_module.ImportReport(
        dry_run=True,
        tables=(
            import_module.TableImportResult(
                table_name="rating",
                source_count=2,
                target_count=0,
            ),
        ),
    )

    def record_import(source_url, target_url, *, dry_run, required_source_tables):
        import_calls.append((source_url, target_url, dry_run, tuple(required_source_tables)))
        return report

    monkeypatch.setattr(import_module, "import_database", record_import)

    exit_code = import_module.main(
        [
            "--source-url",
            "mysql+mysqlconnector://source",
            "--target-url",
            "postgresql+psycopg://target",
            "--dry-run",
            "--require-source-rows",
            "rating",
            "--require-source-rows",
            "record",
        ]
    )

    assert exit_code == 0
    assert import_calls == [
        (
            "mysql+mysqlconnector://source",
            "postgresql+psycopg://target",
            True,
            ("rating", "record"),
        )
    ]


def test_main_fails_report_path_preflight_before_importing(
    import_module,
    monkeypatch,
    tmp_path,
):
    import_calls = []
    monkeypatch.setattr(
        import_module,
        "import_database",
        lambda source_url, target_url, *, dry_run, required_source_tables: import_calls.append(
            (source_url, target_url, dry_run, required_source_tables)
        ),
    )
    report_path = tmp_path / "existing-directory"
    report_path.mkdir()

    with pytest.raises(IsADirectoryError):
        import_module.main(
            [
                "--source-url",
                "mysql+mysqlconnector://source",
                "--target-url",
                "postgresql+psycopg://target",
                "--report-json",
                str(report_path),
            ]
        )

    assert import_calls == []


def test_read_rows_supports_table_without_primary_key(import_module):
    metadata = sqlalchemy.MetaData()
    table = sqlalchemy.Table(
        "audit",
        metadata,
        sqlalchemy.Column("value", sqlalchemy.String()),
    )
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(table.insert(), [{"value": "first"}, {"value": "second"}])
        with engine.connect() as connection:
            assert import_module._read_rows(connection, table) == [
                {"value": "first"},
                {"value": "second"},
            ]
    finally:
        engine.dispose()


def test_reset_postgres_sequence_advances_single_primary_key(import_module, schema_module):
    class ScalarResult:
        def scalar_one(self):
            return "user_user_id_seq"

    class FakeConnection:
        def __init__(self):
            self.dialect = postgresql.dialect()
            self.calls = []

        def execute(self, statement, parameters=None):
            self.calls.append((str(statement), parameters))
            return ScalarResult()

    connection = FakeConnection()

    import_module._reset_postgres_sequence(
        connection,
        schema_module.CURRENT_TARGET_TABLES["user"],
    )

    assert connection.calls[0] == (
        "select pg_get_serial_sequence(:table_name, :column_name)",
        {"table_name": '"user"', "column_name": "user_id"},
    )
    assert "setval" in connection.calls[1][0]
    assert 'from "user"' in connection.calls[1][0]
    assert connection.calls[1][1] == {"sequence_name": "user_user_id_seq"}


def test_reset_postgres_sequence_skips_composite_primary_key(import_module):
    metadata = sqlalchemy.MetaData()
    table = sqlalchemy.Table(
        "composite",
        metadata,
        sqlalchemy.Column("left_id", sqlalchemy.Integer(), primary_key=True),
        sqlalchemy.Column("right_id", sqlalchemy.Integer(), primary_key=True),
    )

    class FakeConnection:
        dialect = postgresql.dialect()

        def execute(self, _statement, _parameters=None):
            raise AssertionError("composite keys must not query for a sequence")

    import_module._reset_postgres_sequence(FakeConnection(), table)


def test_reset_postgres_sequence_skips_table_without_sequence(import_module, schema_module):
    class ScalarResult:
        def scalar_one(self):
            return None

    class FakeConnection:
        def __init__(self):
            self.dialect = postgresql.dialect()
            self.calls = []

        def execute(self, statement, parameters=None):
            self.calls.append((str(statement), parameters))
            return ScalarResult()

    connection = FakeConnection()

    import_module._reset_postgres_sequence(
        connection,
        schema_module.CURRENT_TARGET_TABLES["record"],
    )

    assert len(connection.calls) == 1
