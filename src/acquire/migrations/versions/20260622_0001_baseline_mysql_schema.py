"""Packaged baseline Acquire schema.

Revision ID: 20260622_0001
Revises:
Create Date: 2026-06-22 00:00:00.000000
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql, postgresql

revision = "20260622_0001"
down_revision = None
branch_labels = None
depends_on = None

MYSQL_TABLE_OPTIONS: dict[str, Any] = {
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_bin",
}
UNSIGNED_INTEGER_MAX = 4_294_967_295
UNSIGNED_SMALL_INTEGER_MAX = 65_535
UNSIGNED_TINY_INTEGER_MAX = 255


def _table_options() -> dict[str, Any]:
    """Return dialect-specific table options for the active migration bind.

    MySQL keeps the historical binary collation contract. Other database
    engines use their default table options so the baseline revision can run
    during Postgres parity testing.

    Returns:
        MySQL table options for MySQL binds, otherwise an empty mapping.
    """
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        return MYSQL_TABLE_OPTIONS
    return {}


def _unsigned_range_constraint(
    table_name: str,
    column_name: str,
    max_value: int,
) -> sa.CheckConstraint:
    """Return a database-level range check for a MySQL unsigned column.

    Postgres has no unsigned integer types. These constraints preserve the
    value ranges from the existing MySQL schema when the baseline is applied to
    Postgres. MySQL keeps its native unsigned definitions and cannot attach
    check constraints to auto-increment columns, so the constraint is emitted
    only for Postgres.

    Args:
        table_name: Table that owns the constrained column.
        column_name: Unsigned column name.
        max_value: Highest value accepted by the matching MySQL unsigned type.

    Returns:
        SQLAlchemy check constraint for the unsigned range.
    """
    return sa.CheckConstraint(
        f"{column_name} >= 0 and {column_name} <= {max_value}",
        name=f"ck_{table_name}_{column_name}_unsigned",
    ).ddl_if(dialect="postgresql")


def _unsigned_integer() -> sa.BigInteger:
    """Return a portable integer that keeps MySQL unsigned DDL."""
    return sa.BigInteger().with_variant(mysql.INTEGER(unsigned=True), "mysql")


def _unsigned_small_integer() -> sa.Integer:
    """Return a portable small integer that keeps MySQL unsigned DDL."""
    return sa.Integer().with_variant(mysql.SMALLINT(unsigned=True), "mysql")


def _unsigned_tiny_integer() -> sa.SmallInteger:
    """Return a portable lookup integer that keeps MySQL unsigned TINYINT DDL."""
    return sa.SmallInteger().with_variant(mysql.TINYINT(unsigned=True), "mysql")


def _float() -> sa.Float:
    """Return a portable float that keeps MySQL FLOAT DDL."""
    return sa.Float().with_variant(mysql.FLOAT(), "mysql").with_variant(
        postgresql.REAL(), "postgresql"
    )

game_mode_table = sa.table("game_mode", sa.column("name", sa.String(length=8)))
game_state_table = sa.table("game_state", sa.column("name", sa.String(length=16)))
rating_type_table = sa.table("rating_type", sa.column("name", sa.String(length=8)))


def upgrade() -> None:
    """Create the existing Acquire schema and required lookup rows."""
    op.create_table(
        "game_mode",
        sa.Column("game_mode_id", _unsigned_tiny_integer(), nullable=False),
        sa.Column("name", sa.String(length=8), nullable=False),
        _unsigned_range_constraint("game_mode", "game_mode_id", UNSIGNED_TINY_INTEGER_MAX),
        sa.PrimaryKeyConstraint("game_mode_id"),
        sa.UniqueConstraint("name"),
        **_table_options(),
    )
    op.create_table(
        "game_state",
        sa.Column("game_state_id", _unsigned_tiny_integer(), nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        _unsigned_range_constraint("game_state", "game_state_id", UNSIGNED_TINY_INTEGER_MAX),
        sa.PrimaryKeyConstraint("game_state_id"),
        sa.UniqueConstraint("name"),
        **_table_options(),
    )
    op.create_table(
        "key_value",
        sa.Column("key_value_id", _unsigned_tiny_integer(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        _unsigned_range_constraint("key_value", "key_value_id", UNSIGNED_TINY_INTEGER_MAX),
        sa.PrimaryKeyConstraint("key_value_id"),
        sa.UniqueConstraint("key"),
        **_table_options(),
    )
    op.create_table(
        "rating_type",
        sa.Column("rating_type_id", _unsigned_tiny_integer(), nullable=False),
        sa.Column("name", sa.String(length=8), nullable=False),
        _unsigned_range_constraint("rating_type", "rating_type_id", UNSIGNED_TINY_INTEGER_MAX),
        sa.PrimaryKeyConstraint("rating_type_id"),
        sa.UniqueConstraint("name"),
        **_table_options(),
    )
    op.create_table(
        "user",
        sa.Column("user_id", _unsigned_integer(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("password", sa.String(length=64), nullable=True),
        _unsigned_range_constraint("user", "user_id", UNSIGNED_INTEGER_MAX),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("name"),
        **_table_options(),
    )
    op.create_table(
        "game",
        sa.Column("game_id", _unsigned_integer(), nullable=False),
        sa.Column("log_time", _unsigned_integer(), nullable=False),
        sa.Column("number", _unsigned_integer(), nullable=False),
        sa.Column("begin_time", _unsigned_integer(), nullable=True),
        sa.Column("end_time", _unsigned_integer(), nullable=True),
        sa.Column("game_state_id", _unsigned_tiny_integer(), nullable=False),
        sa.Column("game_mode_id", _unsigned_tiny_integer(), nullable=False),
        _unsigned_range_constraint("game", "game_id", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("game", "log_time", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("game", "number", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("game", "begin_time", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("game", "end_time", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("game", "game_state_id", UNSIGNED_TINY_INTEGER_MAX),
        _unsigned_range_constraint("game", "game_mode_id", UNSIGNED_TINY_INTEGER_MAX),
        sa.ForeignKeyConstraint(["game_mode_id"], ["game_mode.game_mode_id"]),
        sa.ForeignKeyConstraint(["game_state_id"], ["game_state.game_state_id"]),
        sa.PrimaryKeyConstraint("game_id"),
        sa.UniqueConstraint("log_time", "number"),
        **_table_options(),
    )
    op.create_index("end_time", "game", ["end_time"], unique=False)
    op.create_table(
        "rating",
        sa.Column("rating_id", _unsigned_integer(), nullable=False),
        sa.Column("user_id", _unsigned_integer(), nullable=False),
        sa.Column("rating_type_id", _unsigned_tiny_integer(), nullable=False),
        sa.Column("time", _unsigned_integer(), nullable=False),
        sa.Column("mu", _float(), nullable=False),
        sa.Column("sigma", _float(), nullable=False),
        _unsigned_range_constraint("rating", "rating_id", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("rating", "user_id", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("rating", "rating_type_id", UNSIGNED_TINY_INTEGER_MAX),
        _unsigned_range_constraint("rating", "time", UNSIGNED_INTEGER_MAX),
        sa.ForeignKeyConstraint(["rating_type_id"], ["rating_type.rating_type_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"]),
        sa.PrimaryKeyConstraint("rating_id"),
        **_table_options(),
    )
    op.create_index(
        "user_id_rating_type_id",
        "rating",
        ["user_id", "rating_type_id"],
        unique=False,
    )
    op.create_table(
        "record",
        sa.Column("user_id", _unsigned_integer(), nullable=False),
        sa.Column("encoded", sa.String(length=255), nullable=False),
        _unsigned_range_constraint("record", "user_id", UNSIGNED_INTEGER_MAX),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"]),
        sa.PrimaryKeyConstraint("user_id"),
        **_table_options(),
    )
    op.create_table(
        "game_player",
        sa.Column("game_player_id", _unsigned_integer(), nullable=False),
        sa.Column("game_id", _unsigned_integer(), nullable=False),
        sa.Column("player_index", _unsigned_tiny_integer(), nullable=False),
        sa.Column("user_id", _unsigned_integer(), nullable=False),
        sa.Column("score", _unsigned_small_integer(), nullable=True),
        _unsigned_range_constraint("game_player", "game_player_id", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("game_player", "game_id", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("game_player", "player_index", UNSIGNED_TINY_INTEGER_MAX),
        _unsigned_range_constraint("game_player", "user_id", UNSIGNED_INTEGER_MAX),
        _unsigned_range_constraint("game_player", "score", UNSIGNED_SMALL_INTEGER_MAX),
        sa.ForeignKeyConstraint(["game_id"], ["game.game_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"]),
        sa.PrimaryKeyConstraint("game_player_id"),
        sa.UniqueConstraint("game_id", "player_index"),
        **_table_options(),
    )
    op.bulk_insert(
        game_mode_table,
        [
            {"name": "Singles"},
            {"name": "Teams"},
        ],
    )
    op.bulk_insert(
        game_state_table,
        [
            {"name": "Starting"},
            {"name": "StartingFull"},
            {"name": "InProgress"},
            {"name": "Completed"},
        ],
    )
    op.bulk_insert(
        rating_type_table,
        [
            {"name": "Singles2"},
            {"name": "Singles3"},
            {"name": "Singles4"},
            {"name": "Teams"},
        ],
    )


def downgrade() -> None:
    """Drop the existing Acquire schema."""
    op.drop_table("game_player")
    op.drop_table("record")
    op.drop_table("rating")
    op.drop_table("game")
    op.drop_table("user")
    op.drop_table("rating_type")
    op.drop_table("key_value")
    op.drop_table("game_state")
    op.drop_table("game_mode")
