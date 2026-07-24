"""Copy Acquire application tables from MySQL into an empty Postgres database."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql.schema import Table

from acquire import orm

TABLE_ORDER = (
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
BASELINE_LOOKUP_TABLES = frozenset({"game_mode", "game_state", "rating_type"})


@dataclass(frozen=True)
class TableImportResult:
    """Describe import counts for one application table."""

    table_name: str
    source_count: int
    target_count: int


@dataclass(frozen=True)
class ImportReport:
    """Describe the result of a MySQL-to-Postgres import rehearsal."""

    dry_run: bool
    tables: tuple[TableImportResult, ...]

    @property
    def total_rows(self) -> int:
        """Return the total number of source rows covered by the report."""
        return sum(table.source_count for table in self.tables)


class TargetNotEmptyError(RuntimeError):
    """Raised when the target database already contains application data."""


class ImportValidationError(RuntimeError):
    """Raised when source and target counts do not match after import."""


def import_database(
    source_url: str,
    target_url: str,
    *,
    dry_run: bool = False,
    required_source_tables: Sequence[str] = (),
) -> ImportReport:
    """Copy application tables from a source database to an empty target database.

    The target database must already have the current Alembic schema applied.
    Non-lookup application tables must be empty. Baseline lookup tables may
    already contain Alembic-seeded rows when those rows exactly match the
    source. This protects cutover rehearsals from accidentally merging data into
    an existing Postgres database while still supporting the normal migrated
    target shape. Rows are copied with explicit primary keys so historical game,
    user, rating, and foreign-key identities remain stable.

    Args:
        source_url: SQLAlchemy URL for the source MySQL-compatible database.
        target_url: SQLAlchemy URL for the target Postgres-compatible database.
        dry_run: When `True`, validate the target and report source counts
            without inserting rows.
        required_source_tables: Table names that must have at least one source
            row before the import can proceed.

    Returns:
        Import report containing per-table counts.

    Raises:
        TargetNotEmptyError: If any target application table already has rows.
        ImportValidationError: If post-import target counts differ from source
            counts.
    """
    source_engine = sqlalchemy.create_engine(source_url)
    target_engine = sqlalchemy.create_engine(target_url)
    try:
        return import_engines(
            source_engine,
            target_engine,
            dry_run=dry_run,
            required_source_tables=required_source_tables,
        )
    finally:
        source_engine.dispose()
        target_engine.dispose()


def import_engines(
    source_engine: Engine,
    target_engine: Engine,
    *,
    dry_run: bool = False,
    required_source_tables: Sequence[str] = (),
) -> ImportReport:
    """Copy application tables between already-created SQLAlchemy engines.

    This lower-level entry point is used by tests and cutover tooling that
    already manages engine lifetimes. The copy runs in one target transaction,
    so an insert or validation failure leaves the target unchanged. Existing
    Alembic-seeded lookup rows are accepted only when they exactly match the
    source lookup rows.

    Args:
        source_engine: SQLAlchemy engine bound to the source database.
        target_engine: SQLAlchemy engine bound to the target database.
        dry_run: When `True`, report source counts without inserting rows.
        required_source_tables: Table names that must have at least one source
            row before the import can proceed.

    Returns:
        Import report containing per-table counts.

    Raises:
        TargetNotEmptyError: If any target application table already has rows.
        ImportValidationError: If post-import target counts differ from source
            counts.
    """
    results: list[TableImportResult] = []
    tables = _ordered_tables(TABLE_ORDER)

    with source_engine.connect() as source_connection, target_engine.begin() as target_connection:
        _validate_source_tables(source_connection, tables)
        _validate_required_source_tables(
            source_connection,
            tables,
            required_source_tables,
        )
        for table in tables:
            rows = _read_rows(source_connection, table)
            target_rows = _read_rows(target_connection, table)
            _validate_target_table(table, rows, target_rows)
            if not dry_run and rows and not target_rows:
                target_connection.execute(table.insert(), rows)

            target_count = _count_rows(target_connection, table)
            source_count = len(rows)
            if not dry_run and target_count != source_count:
                raise ImportValidationError(
                    f"{table.name} imported {target_count} rows; expected {source_count}"
                )
            if not dry_run:
                _reset_postgres_sequence(target_connection, table)
            results.append(
                TableImportResult(
                    table_name=table.name,
                    source_count=source_count,
                    target_count=target_count,
                )
            )

    return ImportReport(dry_run=dry_run, tables=tuple(results))


def _ordered_tables(table_names: Sequence[str]) -> tuple[Table, ...]:
    """Return ORM tables in the requested copy order.

    Args:
        table_names: Application table names in foreign-key-safe copy order.

    Returns:
        Tuple of SQLAlchemy table objects.
    """
    return tuple(orm.Base.metadata.tables[table_name] for table_name in table_names)


def _validate_required_source_tables(
    connection: Connection,
    tables: tuple[Table, ...],
    table_names: Sequence[str],
) -> None:
    """Validate that required source tables contain rows before copying.

    This guard is intended for production-like rehearsals where sparse staging
    dumps should fail before target mutation. In particular, persisted ratings
    and derived records are required to prove historical stats will survive the
    cutover.

    Args:
        connection: SQLAlchemy connection bound to the source database.
        tables: Application tables expected by the import workflow.
        table_names: Table names that must have source rows.

    Raises:
        ImportValidationError: If a required source table is unknown or empty.
    """
    tables_by_name = {table.name: table for table in tables}
    for table_name in table_names:
        table = tables_by_name.get(table_name)
        if table is None:
            raise ImportValidationError(f"{table_name}: required source table is unknown")
        if _count_rows(connection, table) == 0:
            raise ImportValidationError(f"{table_name}: required source table has no rows")


def _validate_source_tables(connection: Connection, tables: tuple[Table, ...]) -> None:
    """Validate that the source database has every import table.

    The importer requires every application table, including the derived
    `record` table. Runtime stats reads do not rebuild historical record rows
    from imported games, so accepting a source without `record` would silently
    reset win/place stats after cutover.

    Args:
        connection: SQLAlchemy connection bound to the source database.
        tables: Application tables expected by the import workflow.

    Raises:
        ImportValidationError: If the source database is missing a required
            application table.
    """
    source_table_names = set(sqlalchemy.inspect(connection).get_table_names())
    missing_required_tables = [
        table.name
        for table in tables
        if table.name not in source_table_names
    ]
    if missing_required_tables:
        raise ImportValidationError(
            "source database is missing required tables: "
            + ", ".join(missing_required_tables)
        )


def _validate_target_table(
    table: Table,
    source_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
) -> None:
    """Raise when a target table is not safe to import into.

    Args:
        table: Application table being imported.
        source_rows: Rows read from the source database.
        target_rows: Rows already present in the target database.

    Raises:
        TargetNotEmptyError: If a mutable table already contains rows.
        ImportValidationError: If a baseline lookup table has unexpected rows.
    """
    if not target_rows:
        return
    if table.name not in BASELINE_LOOKUP_TABLES:
        raise TargetNotEmptyError(f"target table must be empty before import: {table.name}")
    if target_rows != source_rows:
        raise ImportValidationError(
            f"target lookup table {table.name} does not match source rows"
        )


def _read_rows(connection: Connection, table: Table) -> list[dict[str, object]]:
    """Return all rows for a table as dictionaries keyed by column name.

    Args:
        connection: SQLAlchemy connection bound to the source database.
        table: SQLAlchemy table to read.

    Returns:
        List of row dictionaries in primary-key order when the table has a
        primary key, otherwise database order.
    """
    statement = sqlalchemy.select(table)
    primary_key_columns = list(table.primary_key.columns)
    if primary_key_columns:
        statement = statement.order_by(*primary_key_columns)
    rows = connection.execute(statement)
    return [dict(row._mapping) for row in rows]


def _count_rows(connection: Connection, table: Table) -> int:
    """Return the number of rows in a table.

    Args:
        connection: SQLAlchemy connection bound to a database.
        table: SQLAlchemy table to count.

    Returns:
        Number of rows currently present in the table.
    """
    statement = sqlalchemy.select(sqlalchemy.func.count()).select_from(table)
    return int(connection.execute(statement).scalar_one())


def _reset_postgres_sequence(connection: Connection, table: Table) -> None:
    """Advance a Postgres primary-key sequence after explicit id inserts.

    The import preserves MySQL primary keys so historical foreign keys stay
    stable. On Postgres, inserting explicit ids does not necessarily advance the
    backing sequence used for future inserts. This helper uses Postgres'
    `pg_get_serial_sequence` so tables without a sequence are ignored.

    Args:
        connection: SQLAlchemy connection bound to the target database.
        table: Imported SQLAlchemy table whose primary key may have a sequence.
    """
    if connection.dialect.name != "postgresql":
        return

    primary_key_columns = list(table.primary_key.columns)
    if len(primary_key_columns) != 1:
        return

    primary_key_column = primary_key_columns[0]
    preparer = connection.dialect.identifier_preparer
    quoted_table = preparer.quote(table.name)
    quoted_column = preparer.quote(primary_key_column.name)
    sequence_name = connection.execute(
        sqlalchemy.text("select pg_get_serial_sequence(:table_name, :column_name)"),
        {"table_name": quoted_table, "column_name": primary_key_column.name},
    ).scalar_one()
    if sequence_name is None:
        return

    connection.execute(
        sqlalchemy.text(
            f"""
            select setval(
                :sequence_name,
                coalesce(max({quoted_column}), 1),
                max({quoted_column}) is not null
            )
            from {quoted_table}
            """
        ),
        {"sequence_name": sequence_name},
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the import tool.

    Args:
        argv: Optional argument list for tests. Defaults to process arguments.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(
        description="Copy Acquire application rows from MySQL into an empty Postgres database."
    )
    parser.add_argument("--source-url", required=True, help="SQLAlchemy URL for the MySQL source")
    parser.add_argument(
        "--target-url",
        required=True,
        help="SQLAlchemy URL for the Postgres target",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the target and report counts without inserting rows",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Write a sanitized JSON report containing import mode and table counts",
    )
    parser.add_argument(
        "--require-source-rows",
        action="append",
        default=[],
        choices=TABLE_ORDER,
        metavar="TABLE",
        help="Require TABLE to have at least one source row before importing",
    )
    return parser.parse_args(argv)


def write_report_json(report: ImportReport, path: Path) -> None:
    """Write a sanitized import report as JSON.

    The report intentionally contains only table names, source counts, target
    counts, dry-run mode, and total row count. It excludes connection URLs,
    hostnames, credentials, and filesystem paths so rehearsal evidence can be
    referenced from PRs or project notes without leaking environment details.

    Args:
        report: Import report returned by the rehearsal command.
        path: Destination JSON path.
    """
    payload = {
        "dry_run": report.dry_run,
        "total_rows": report.total_rows,
        "tables": [
            {
                "table_name": table.table_name,
                "source_count": table.source_count,
                "target_count": table.target_count,
            }
            for table in report.tables
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def preflight_report_json_path(path: Path) -> None:
    """Validate that the JSON report destination is writable before import.

    Non-dry-run imports commit data before the command can write its final
    evidence report. This preflight creates parent directories and opens the
    destination for writing first so an invalid path fails before database
    mutation starts. The final report write later replaces this empty probe
    file with the sanitized JSON payload.

    Args:
        path: Destination JSON path requested by the operator.

    Raises:
        OSError: If the path cannot be created, opened, or written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w"):
        pass


def main(argv: Sequence[str] | None = None) -> int:
    """Run the import command-line interface.

    Args:
        argv: Optional argument list for tests. Defaults to process arguments.

    Returns:
        Process exit code.
    """
    args = parse_args(argv)
    if args.report_json is not None:
        preflight_report_json_path(args.report_json)
    report = import_database(
        args.source_url,
        args.target_url,
        dry_run=args.dry_run,
        required_source_tables=args.require_source_rows,
    )
    mode = "dry run" if report.dry_run else "import"
    print(f"{mode} covered {report.total_rows} rows")
    for table in report.tables:
        print(f"{table.table_name}: source={table.source_count} target={table.target_count}")
    if args.report_json is not None:
        write_report_json(report, args.report_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
