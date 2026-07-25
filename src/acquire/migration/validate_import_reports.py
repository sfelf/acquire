"""Validate sanitized MySQL-to-Postgres import rehearsal reports."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Never

from acquire.migration.import_mysql_to_postgres import (
    BASELINE_LOOKUP_TABLES,
    TABLE_ORDER,
)

REPORT_KEYS = frozenset({"dry_run", "total_rows", "tables"})
TABLE_KEYS = frozenset({"table_name", "source_count", "target_count"})
EXPECTED_TABLE_ORDER = tuple(TABLE_ORDER)

EXIT_SUCCESS = 0
EXIT_INVALID_INPUT = 2
EXIT_VALIDATION_FAILED = 7


class CommandArgumentError(ValueError):
    """Raised when command arguments do not satisfy the validator contract."""


class SafeArgumentParser(argparse.ArgumentParser):
    """Reject invalid arguments without reflecting untrusted values."""

    def error(self, message: str) -> Never:
        """Raise a fixed argument error without projecting parser input.

        Args:
            message: Argparse's detailed error, intentionally excluded because
                it may contain a private path or encoded sensitive value.

        Raises:
            CommandArgumentError: Always.
        """
        del message
        raise CommandArgumentError("invalid command arguments")


class ReportValidationError(RuntimeError):
    """Raised when an import rehearsal report is malformed or inconsistent."""


@dataclass(frozen=True)
class TableCounts:
    """Represent sanitized count data for one imported table."""

    table_name: str
    source_count: int
    target_count: int


@dataclass(frozen=True)
class ImportReport:
    """Represent a sanitized import rehearsal report."""

    dry_run: bool
    total_rows: int
    tables: tuple[TableCounts, ...]


def load_report(path: Path, *, context: str = "report") -> ImportReport:
    """Load and validate a sanitized import rehearsal report.

    Report files are intended to be safe to reference from project notes or PR
    summaries. This parser rejects unexpected fields so connection URLs,
    credentials, backup paths, hostnames, or row contents cannot quietly become
    part of the accepted report contract.

    Args:
        path: JSON report path to load.
        context: Maintainer-controlled label used in validation diagnostics.

    Returns:
        Parsed import report.

    Raises:
        ReportValidationError: If the JSON payload is malformed or contains
            unexpected fields.
    """
    try:
        payload = json.loads(path.read_text(), object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ReportValidationError(f"{context}: invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ReportValidationError(f"{context}: report must be a JSON object")
    _validate_keys(context, payload, REPORT_KEYS)

    dry_run = payload["dry_run"]
    total_rows = payload["total_rows"]
    tables = payload["tables"]
    if not isinstance(dry_run, bool):
        raise ReportValidationError(f"{context}: dry_run must be a boolean")
    if not _is_nonnegative_int(total_rows):
        raise ReportValidationError(f"{context}: total_rows must be a non-negative integer")
    if not isinstance(tables, list):
        raise ReportValidationError(f"{context}: tables must be a list")

    parsed_tables = tuple(
        _parse_table(context, index, table) for index, table in enumerate(tables)
    )
    _validate_table_order(context, parsed_tables)
    source_total = sum(table.source_count for table in parsed_tables)
    if source_total != total_rows:
        raise ReportValidationError(
            f"{context}: total_rows {total_rows} does not match source row total {source_total}"
        )
    return ImportReport(dry_run=dry_run, total_rows=total_rows, tables=parsed_tables)


def validate_report_pair(
    dry_run_report: ImportReport,
    import_report: ImportReport,
    *,
    required_source_tables: Sequence[str] = (),
) -> None:
    """Validate that dry-run and import reports describe the same source data.

    The dry-run report proves the source row counts reviewed before mutation.
    The import report proves those same rows were copied and counted in the
    target. This check intentionally compares counts only; it does not inspect
    row contents or require private backup data. Operators can require
    non-empty source counts for critical tables, such as persisted rating and
    record stats, so a sparse staging dump cannot accidentally satisfy a
    production-like rehearsal gate.

    Args:
        dry_run_report: Report produced with `--dry-run`.
        import_report: Report produced by the completed import.
        required_source_tables: Table names that must have at least one source
            row in both reports.

    Raises:
        ReportValidationError: If modes, table order, source counts, totals, or
            imported target counts are inconsistent, or if a required source
            table has no source rows.
    """
    if not dry_run_report.dry_run:
        raise ReportValidationError("dry-run report must have dry_run=true")
    if import_report.dry_run:
        raise ReportValidationError("import report must have dry_run=false")
    if len(dry_run_report.tables) != len(import_report.tables):
        raise ReportValidationError("report table counts differ")
    if dry_run_report.total_rows != import_report.total_rows:
        raise ReportValidationError("report total_rows values differ")
    _validate_table_order("dry-run report", dry_run_report.tables)
    _validate_table_order("import report", import_report.tables)
    _validate_dry_run_target_counts(dry_run_report)

    for dry_run_table, import_table in zip(
        dry_run_report.tables,
        import_report.tables,
        strict=True,
    ):
        if dry_run_table.source_count != import_table.source_count:
            raise ReportValidationError(
                f"{dry_run_table.table_name}: source counts differ "
                f"({dry_run_table.source_count} != {import_table.source_count})"
            )
        if import_table.target_count != import_table.source_count:
            raise ReportValidationError(
                f"{import_table.table_name}: imported target count "
                f"{import_table.target_count} does not match source count "
                f"{import_table.source_count}"
            )
    _validate_required_source_tables(import_report, required_source_tables)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for report validation.

    Args:
        argv: Optional argument list for tests. Defaults to process arguments.

    Returns:
        Parsed command-line namespace.
    """
    parser = SafeArgumentParser(
        description="Validate sanitized MySQL-to-Postgres import rehearsal reports."
    )
    parser.add_argument("--dry-run-report", required=True, type=Path)
    parser.add_argument("--import-report", required=True, type=Path)
    parser.add_argument(
        "--require-source-rows",
        action="append",
        default=[],
        choices=EXPECTED_TABLE_ORDER,
        metavar="TABLE",
        help="Require TABLE to have at least one source row in the validated reports",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run report validation with fixed, non-sensitive diagnostics.

    Report paths, unexpected fields, decoded data, and exception details are
    excluded from stderr. Validation failures use one printable, single-line
    marker so redaction is idempotent for raw and encoded unsafe inputs.

    Args:
        argv: Optional argument list for tests. Defaults to process arguments.

    Returns:
        Process exit code.
    """
    try:
        args = parse_args(argv)
    except CommandArgumentError:
        return _command_error(EXIT_INVALID_INPUT, "invalid command arguments")

    try:
        dry_run_report = load_report(args.dry_run_report, context="dry-run report")
        import_report = load_report(args.import_report, context="import report")
        validate_report_pair(
            dry_run_report,
            import_report,
            required_source_tables=args.require_source_rows,
        )
    except (OSError, ReportValidationError):
        return _command_error(EXIT_VALIDATION_FAILED, "report validation failed")

    print(
        "validated import reports for "
        f"{import_report.total_rows} rows across {len(import_report.tables)} tables"
    )
    return EXIT_SUCCESS


def _command_error(exit_code: int, marker: str) -> int:
    """Write one fixed diagnostic marker and return its exit code.

    Args:
        exit_code: Stable nonzero command exit code.
        marker: Maintainer-controlled diagnostic text.

    Returns:
        The supplied exit code.
    """
    print(f"error: {marker}", file=sys.stderr)
    return exit_code


def _validate_required_source_tables(
    import_report: ImportReport,
    table_names: Sequence[str],
) -> None:
    """Validate that required source tables are represented by nonzero counts.

    Args:
        import_report: Parsed completed-import report.
        table_names: Table names that must have source rows.

    Raises:
        ReportValidationError: If a required table has zero source rows.
    """
    counts_by_table = {table.table_name: table.source_count for table in import_report.tables}
    for table_name in table_names:
        if table_name not in counts_by_table:
            raise ReportValidationError(f"{table_name}: required source table is unknown")
        if counts_by_table[table_name] == 0:
            raise ReportValidationError(
                f"{table_name}: required source table has no rows"
            )


def _parse_table(context: str, index: int, payload: object) -> TableCounts:
    """Parse one table-count entry from a report.

    Args:
        context: Maintainer-controlled report label used in validation messages.
        index: Position of the table entry in the report.
        payload: Raw JSON value for the table entry.

    Returns:
        Parsed table-count entry.

    Raises:
        ReportValidationError: If the table entry is malformed.
    """
    if not isinstance(payload, Mapping):
        raise ReportValidationError(f"{context}: tables[{index}] must be an object")
    _validate_keys(context, payload, TABLE_KEYS, prefix=f"tables[{index}]")

    table_name = payload["table_name"]
    source_count = payload["source_count"]
    target_count = payload["target_count"]
    if not isinstance(table_name, str) or not table_name:
        raise ReportValidationError(
            f"{context}: tables[{index}].table_name must be a string"
        )
    if not _is_nonnegative_int(source_count):
        raise ReportValidationError(
            f"{context}: tables[{index}].source_count must be a non-negative integer"
        )
    if not _is_nonnegative_int(target_count):
        raise ReportValidationError(
            f"{context}: tables[{index}].target_count must be a non-negative integer"
        )
    return TableCounts(
        table_name=table_name,
        source_count=source_count,
        target_count=target_count,
    )


def _validate_table_order(context: object, tables: tuple[TableCounts, ...]) -> None:
    """Validate that report tables match the import tool's table order.

    Args:
        context: Report path or label used in validation messages.
        tables: Parsed table-count entries.

    Raises:
        ReportValidationError: If table names are missing, duplicated,
            unexpected, or out of order.
    """
    table_names = tuple(table.table_name for table in tables)
    if table_names != EXPECTED_TABLE_ORDER:
        raise ReportValidationError(
            f"{context}: tables must match expected order: {', '.join(EXPECTED_TABLE_ORDER)}"
        )


def _validate_dry_run_target_counts(dry_run_report: ImportReport) -> None:
    """Validate dry-run target counts against the expected empty target shape.

    Lookup tables may already contain Alembic-seeded rows matching the source.
    Mutable application tables must be empty during the dry run, otherwise the
    rehearsal did not prove the target was safe to import into.

    Args:
        dry_run_report: Parsed dry-run report.

    Raises:
        ReportValidationError: If a lookup table count is inconsistent or a
            mutable table is not empty.
    """
    for table in dry_run_report.tables:
        if table.table_name in BASELINE_LOOKUP_TABLES:
            if table.target_count not in (0, table.source_count):
                raise ReportValidationError(
                    f"{table.table_name}: dry-run lookup target count {table.target_count} "
                    f"must be 0 or match source count {table.source_count}"
                )
        elif table.target_count != 0:
            raise ReportValidationError(
                f"{table.table_name}: dry-run target count {table.target_count} "
                "must be 0 for mutable tables"
            )


def _validate_keys(
    context: str,
    payload: Mapping[object, object],
    expected_keys: frozenset[str],
    *,
    prefix: str = "report",
) -> None:
    """Validate that a JSON object has exactly the expected keys.

    Args:
        context: Maintainer-controlled report label used in validation messages.
        payload: JSON object to inspect.
        expected_keys: Exact key set required for the object.
        prefix: Human-readable object label for validation messages.

    Raises:
        ReportValidationError: If any expected key is missing or any
            unexpected key is present.
    """
    keys = set(payload)
    if keys != expected_keys:
        missing_keys = sorted(expected_keys - keys)
        details = []
        if keys - expected_keys:
            details.append("unexpected keys")
        if missing_keys:
            details.append(f"missing keys: {', '.join(missing_keys)}")
        raise ReportValidationError(f"{context}: {prefix} has {'; '.join(details)}")


def _reject_duplicate_keys(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    """Return a JSON object while rejecting duplicate keys.

    Args:
        pairs: JSON object key/value pairs in source order.

    Returns:
        Dictionary built from the key/value pairs.

    Raises:
        ReportValidationError: If a key appears more than once in the same JSON
            object.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReportValidationError("duplicate JSON key")
        result[key] = value
    return result


def _is_nonnegative_int(value: object) -> bool:
    """Return whether a value is a non-boolean non-negative integer.

    Args:
        value: Value to inspect.

    Returns:
        `True` when `value` is an `int`, is not a `bool`, and is non-negative.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


if __name__ == "__main__":
    raise SystemExit(main())
