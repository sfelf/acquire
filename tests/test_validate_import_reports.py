import json
from pathlib import Path

import pytest
import validate_import_reports

pytestmark = pytest.mark.unit
SOURCE_COUNTS = {
    table_name: index + 1
    for index, table_name in enumerate(validate_import_reports.EXPECTED_TABLE_ORDER)
}
LOOKUP_TABLES = {"game_mode", "game_state", "rating_type"}


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload))


def expected_total_rows() -> int:
    return sum(SOURCE_COUNTS.values())


def table_payload(table_name: str, *, dry_run: bool) -> dict[str, object]:
    source_count = SOURCE_COUNTS[table_name]
    target_count = (source_count if table_name in LOOKUP_TABLES else 0) if dry_run else source_count
    return {
        "table_name": table_name,
        "source_count": source_count,
        "target_count": target_count,
    }


def report_payload(*, dry_run: bool) -> dict[str, object]:
    return {
        "dry_run": dry_run,
        "total_rows": expected_total_rows(),
        "tables": [
            table_payload(table_name, dry_run=dry_run)
            for table_name in validate_import_reports.EXPECTED_TABLE_ORDER
        ],
    }


def report_model(*, dry_run: bool) -> validate_import_reports.ImportReport:
    payload = report_payload(dry_run=dry_run)
    return validate_import_reports.ImportReport(
        dry_run=dry_run,
        total_rows=expected_total_rows(),
        tables=tuple(
            validate_import_reports.TableCounts(
                table["table_name"],
                table["source_count"],
                table["target_count"],
            )
            for table in payload["tables"]
        ),
    )


def replace_table(
    payload: dict[str, object],
    table_name: str,
    replacement: dict[str, object],
) -> dict[str, object]:
    tables = payload["tables"]
    assert isinstance(tables, list)
    return {
        **payload,
        "tables": [
            replacement if table["table_name"] == table_name else table
            for table in tables
        ],
    }


def test_load_report_accepts_sanitized_report(tmp_path):
    report_path = tmp_path / "report.json"
    write_json(report_path, report_payload(dry_run=True))

    report = validate_import_reports.load_report(report_path)

    assert report == report_model(dry_run=True)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ([], "report must be a JSON object"),
        ({"dry_run": True, "total_rows": 0}, "missing keys: tables"),
        (
            {"dry_run": True, "total_rows": 0, "tables": [], "source_url": "mysql://x"},
            "unexpected keys",
        ),
        ({"dry_run": "yes", "total_rows": 0, "tables": []}, "dry_run must be a boolean"),
        ({"dry_run": True, "total_rows": True, "tables": []}, "total_rows must be"),
        ({"dry_run": True, "total_rows": 0, "tables": {}}, "tables must be a list"),
        (
            {
                "dry_run": True,
                "total_rows": 0,
                "tables": ["not an object"],
            },
            "tables\\[0\\] must be an object",
        ),
        (
            {
                "dry_run": True,
                "total_rows": 0,
                "tables": [
                    {"table_name": "user", "source_count": 0, "target_count": 0, "rows": []}
                ],
            },
            "unexpected keys",
        ),
        (
            {
                "dry_run": True,
                "total_rows": 0,
                "tables": [{"table_name": "", "source_count": 0, "target_count": 0}],
            },
            "table_name must be a string",
        ),
        (
            {
                "dry_run": True,
                "total_rows": 0,
                "tables": [{"table_name": "user", "source_count": -1, "target_count": 0}],
            },
            "source_count must be a non-negative integer",
        ),
        (
            {
                "dry_run": True,
                "total_rows": 0,
                "tables": [{"table_name": "user", "source_count": 0, "target_count": True}],
            },
            "target_count must be a non-negative integer",
        ),
        (
            {
                "dry_run": True,
                "total_rows": 1,
                "tables": report_payload(dry_run=True)["tables"],
            },
            "does not match source row total",
        ),
        (
            replace_table(
                report_payload(dry_run=True),
                "user",
                {
                    "table_name": "mysql://user:password@host/db",
                    "source_count": 1,
                    "target_count": 0,
                },
            ),
            "tables must match expected order",
        ),
        (
            replace_table(
                report_payload(dry_run=True),
                "user",
                {"table_name": "game", "source_count": 1, "target_count": 0},
            ),
            "tables must match expected order",
        ),
    ],
)
def test_load_report_rejects_malformed_or_unsanitized_reports(tmp_path, payload, match):
    report_path = tmp_path / "report.json"
    write_json(report_path, payload)

    with pytest.raises(validate_import_reports.ReportValidationError, match=match):
        validate_import_reports.load_report(report_path)


def test_load_report_rejects_invalid_json(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text("{not json")

    with pytest.raises(validate_import_reports.ReportValidationError, match="invalid JSON"):
        validate_import_reports.load_report(report_path)


@pytest.mark.parametrize(
    ("raw_report", "match"),
    [
        (
            '{"dry_run": true, "dry_run": false, "total_rows": 0, "tables": []}',
            "duplicate JSON key: dry_run",
        ),
        (
            (
                '{"dry_run": true, "total_rows": 0, "tables": ['
                '{"table_name": "user", "source_count": 0, '
                '"source_count": "mysql://user:password@host/db", "target_count": 0}'
                "]}"
            ),
            "duplicate JSON key: source_count",
        ),
    ],
)
def test_load_report_rejects_duplicate_json_keys(tmp_path, raw_report, match):
    report_path = tmp_path / "report.json"
    report_path.write_text(raw_report)

    with pytest.raises(validate_import_reports.ReportValidationError, match=match):
        validate_import_reports.load_report(report_path)


def test_validate_report_pair_accepts_matching_reports():
    dry_run_report = report_model(dry_run=True)
    import_report = report_model(dry_run=False)

    validate_import_reports.validate_report_pair(dry_run_report, import_report)


@pytest.mark.parametrize(
    ("dry_run_report", "import_report", "match"),
    [
        (
            validate_import_reports.ImportReport(
                dry_run=False,
                total_rows=expected_total_rows(),
                tables=report_model(dry_run=False).tables,
            ),
            validate_import_reports.ImportReport(
                dry_run=False,
                total_rows=expected_total_rows(),
                tables=report_model(dry_run=False).tables,
            ),
            "dry-run report must have dry_run=true",
        ),
        (
            report_model(dry_run=True),
            validate_import_reports.ImportReport(
                dry_run=True,
                total_rows=expected_total_rows(),
                tables=report_model(dry_run=False).tables,
            ),
            "import report must have dry_run=false",
        ),
        (
            report_model(dry_run=True),
            validate_import_reports.ImportReport(
                dry_run=False,
                total_rows=expected_total_rows() + 1,
                tables=report_model(dry_run=False).tables,
            ),
            "total_rows values differ",
        ),
        (
            report_model(dry_run=True),
            validate_import_reports.ImportReport(
                dry_run=False,
                total_rows=expected_total_rows(),
                tables=report_model(dry_run=False).tables[:-1],
            ),
            "report table counts differ",
        ),
        (
            report_model(dry_run=True),
            validate_import_reports.ImportReport(
                dry_run=False,
                total_rows=expected_total_rows(),
                tables=(
                    validate_import_reports.TableCounts("game", 1, 1),
                    *report_model(dry_run=False).tables[1:],
                ),
            ),
            "import report: tables must match expected order",
        ),
        (
            validate_import_reports.ImportReport(
                dry_run=True,
                total_rows=expected_total_rows(),
                tables=(
                    validate_import_reports.TableCounts(
                        "mysql://user:password@host/db",
                        SOURCE_COUNTS["game_mode"],
                        SOURCE_COUNTS["game_mode"],
                    ),
                    *report_model(dry_run=True).tables[1:],
                ),
            ),
            validate_import_reports.ImportReport(
                dry_run=False,
                total_rows=expected_total_rows(),
                tables=(
                    validate_import_reports.TableCounts(
                        "mysql://user:password@host/db",
                        SOURCE_COUNTS["game_mode"],
                        SOURCE_COUNTS["game_mode"],
                    ),
                    *report_model(dry_run=False).tables[1:],
                ),
            ),
            "dry-run report: tables must match expected order",
        ),
        (
            report_model(dry_run=True),
            validate_import_reports.ImportReport(
                dry_run=False,
                total_rows=expected_total_rows(),
                tables=(
                    validate_import_reports.TableCounts("game_mode", 0, 0),
                    *report_model(dry_run=False).tables[1:],
                ),
            ),
            "source counts differ",
        ),
        (
            report_model(dry_run=True),
            validate_import_reports.ImportReport(
                dry_run=False,
                total_rows=expected_total_rows(),
                tables=(
                    *report_model(dry_run=False).tables[:3],
                    validate_import_reports.TableCounts("user", SOURCE_COUNTS["user"], 0),
                    *report_model(dry_run=False).tables[4:],
                ),
            ),
            "imported target count 0 does not match source count",
        ),
        (
            validate_import_reports.ImportReport(
                dry_run=True,
                total_rows=expected_total_rows(),
                tables=(
                    *report_model(dry_run=True).tables[:3],
                    validate_import_reports.TableCounts(
                        "user",
                        SOURCE_COUNTS["user"],
                        SOURCE_COUNTS["user"],
                    ),
                    *report_model(dry_run=True).tables[4:],
                ),
            ),
            report_model(dry_run=False),
            "user: dry-run target count",
        ),
        (
            validate_import_reports.ImportReport(
                dry_run=True,
                total_rows=expected_total_rows(),
                tables=(
                    validate_import_reports.TableCounts(
                        "game_mode",
                        SOURCE_COUNTS["game_mode"],
                        SOURCE_COUNTS["game_mode"] + 1,
                    ),
                    *report_model(dry_run=True).tables[1:],
                ),
            ),
            report_model(dry_run=False),
            "game_mode: dry-run lookup target count",
        ),
    ],
)
def test_validate_report_pair_rejects_inconsistent_reports(
    dry_run_report,
    import_report,
    match,
):
    with pytest.raises(validate_import_reports.ReportValidationError, match=match):
        validate_import_reports.validate_report_pair(dry_run_report, import_report)


def test_validate_report_pair_accepts_required_source_tables_with_rows():
    dry_run_report = report_model(dry_run=True)
    import_report = report_model(dry_run=False)

    validate_import_reports.validate_report_pair(
        dry_run_report,
        import_report,
        required_source_tables=["rating", "record"],
    )


def test_validate_report_pair_rejects_required_source_table_without_rows():
    dry_run_report = report_model(dry_run=True)
    import_report = report_model(dry_run=False)
    dry_run_report = validate_import_reports.ImportReport(
        dry_run=True,
        total_rows=dry_run_report.total_rows - SOURCE_COUNTS["record"],
        tables=(
            *dry_run_report.tables[:-1],
            validate_import_reports.TableCounts("record", 0, 0),
        ),
    )
    import_report = validate_import_reports.ImportReport(
        dry_run=False,
        total_rows=import_report.total_rows - SOURCE_COUNTS["record"],
        tables=(
            *import_report.tables[:-1],
            validate_import_reports.TableCounts("record", 0, 0),
        ),
    )

    with pytest.raises(
        validate_import_reports.ReportValidationError,
        match="record: required source table has no rows",
    ):
        validate_import_reports.validate_report_pair(
            dry_run_report,
            import_report,
            required_source_tables=["record"],
        )


def test_validate_report_pair_rejects_unknown_required_source_table():
    dry_run_report = report_model(dry_run=True)
    import_report = report_model(dry_run=False)

    with pytest.raises(
        validate_import_reports.ReportValidationError,
        match="missing_table: required source table is unknown",
    ):
        validate_import_reports.validate_report_pair(
            dry_run_report,
            import_report,
            required_source_tables=["missing_table"],
        )


def test_main_validates_report_files(tmp_path, capsys):
    dry_run_path = tmp_path / "dry-run-report.json"
    import_path = tmp_path / "import-report.json"
    write_json(dry_run_path, report_payload(dry_run=True))
    write_json(import_path, report_payload(dry_run=False))

    exit_code = validate_import_reports.main(
        [
            "--dry-run-report",
            str(dry_run_path),
            "--import-report",
            str(import_path),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == (
        f"validated import reports for {expected_total_rows()} rows across "
        f"{len(validate_import_reports.EXPECTED_TABLE_ORDER)} tables\n"
    )


def test_main_validates_required_source_tables(tmp_path):
    dry_run_path = tmp_path / "dry-run-report.json"
    import_path = tmp_path / "import-report.json"
    write_json(dry_run_path, report_payload(dry_run=True))
    write_json(import_path, report_payload(dry_run=False))

    exit_code = validate_import_reports.main(
        [
            "--dry-run-report",
            str(dry_run_path),
            "--import-report",
            str(import_path),
            "--require-source-rows",
            "rating",
            "--require-source-rows",
            "record",
        ]
    )

    assert exit_code == 0
