import importlib
import json

import pytest
import sqlalchemy
from sqlalchemy.dialects import postgresql

pytestmark = pytest.mark.unit


@pytest.fixture
def import_module():
    return importlib.import_module("import_mysql_to_postgres")


@pytest.fixture
def orm_module():
    return importlib.import_module("orm")


@pytest.fixture
def source_engine(orm_module):
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    orm_module.Base.metadata.create_all(engine)
    seed_source_database(engine, orm_module)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def target_engine(orm_module):
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    orm_module.Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def seed_source_database(engine, orm_module):
    tables = orm_module.Base.metadata.tables
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


def seed_matching_lookup_rows(engine, orm_module):
    tables = orm_module.Base.metadata.tables
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


def table_rows(engine, orm_module, table_name):
    table = orm_module.Base.metadata.tables[table_name]
    primary_key_columns = list(table.primary_key.columns)
    statement = sqlalchemy.select(table).order_by(*primary_key_columns)
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(statement)]


def test_import_engines_copies_rows_into_migrated_postgres_shape(
    import_module,
    orm_module,
    source_engine,
    target_engine,
):
    seed_matching_lookup_rows(target_engine, orm_module)

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
    assert table_rows(target_engine, orm_module, "user") == table_rows(
        source_engine, orm_module, "user"
    )
    assert table_rows(target_engine, orm_module, "game_player") == table_rows(
        source_engine, orm_module, "game_player"
    )
    assert table_rows(target_engine, orm_module, "record") == table_rows(
        source_engine, orm_module, "record"
    )


def test_import_engines_rejects_non_empty_mutable_target_table(
    import_module,
    orm_module,
    source_engine,
    target_engine,
):
    seed_matching_lookup_rows(target_engine, orm_module)
    with target_engine.begin() as connection:
        connection.execute(
            orm_module.Base.metadata.tables["user"].insert(),
            {"user_id": 99, "name": "Existing", "password": None},
        )

    with pytest.raises(
        import_module.TargetNotEmptyError,
        match="target table must be empty before import: user",
    ):
        import_module.import_engines(source_engine, target_engine)

    assert table_rows(target_engine, orm_module, "user") == [
        {"user_id": 99, "name": "Existing", "password": None}
    ]


def test_import_engines_rejects_mismatched_lookup_rows(
    import_module,
    orm_module,
    source_engine,
    target_engine,
):
    with target_engine.begin() as connection:
        connection.execute(
            orm_module.Base.metadata.tables["game_mode"].insert(),
            {"game_mode_id": 1, "name": "Different"},
        )

    with pytest.raises(
        import_module.ImportValidationError,
        match="target lookup table game_mode does not match source rows",
    ):
        import_module.import_engines(source_engine, target_engine)


def test_import_engines_dry_run_reports_counts_without_writing(
    import_module,
    orm_module,
    source_engine,
    target_engine,
):
    seed_matching_lookup_rows(target_engine, orm_module)

    report = import_module.import_engines(source_engine, target_engine, dry_run=True)

    assert report.dry_run is True
    assert report.total_rows == 13
    assert table_rows(target_engine, orm_module, "user") == []
    assert table_rows(target_engine, orm_module, "game") == []


def test_import_database_builds_engines_from_urls(import_module, orm_module, tmp_path):
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    source_engine = sqlalchemy.create_engine(source_url)
    target_engine = sqlalchemy.create_engine(target_url)
    try:
        orm_module.Base.metadata.create_all(source_engine)
        orm_module.Base.metadata.create_all(target_engine)
        seed_source_database(source_engine, orm_module)
        seed_matching_lookup_rows(target_engine, orm_module)
    finally:
        source_engine.dispose()
        target_engine.dispose()

    report = import_module.import_database(source_url, target_url)

    assert report.total_rows == 13
    verify_engine = sqlalchemy.create_engine(target_url)
    try:
        assert table_rows(verify_engine, orm_module, "user") == [
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
        lambda source_url, target_url, *, dry_run: report,
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
        lambda source_url, target_url, *, dry_run: report,
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

    def record_import(source_url, target_url, *, dry_run):
        call_order.append(("import", dry_run))
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
    assert call_order == [("preflight", False), ("import", False)]
    assert json.loads(report_path.read_text())["total_rows"] == 2


def test_main_fails_report_path_preflight_before_importing(
    import_module,
    monkeypatch,
    tmp_path,
):
    import_calls = []
    monkeypatch.setattr(
        import_module,
        "import_database",
        lambda source_url, target_url, *, dry_run: import_calls.append(
            (source_url, target_url, dry_run)
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


def test_reset_postgres_sequence_advances_single_primary_key(import_module, orm_module):
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
        orm_module.Base.metadata.tables["user"],
    )

    assert connection.calls[0] == (
        "select pg_get_serial_sequence(:table_name, :column_name)",
        {"table_name": '"user"', "column_name": "user_id"},
    )
    assert "setval" in connection.calls[1][0]
    assert 'from "user"' in connection.calls[1][0]
    assert connection.calls[1][1] == {"sequence_name": "user_user_id_seq"}
