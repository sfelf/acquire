"""Baseline MySQL schema.

Revision ID: 20260622_0001
Revises:
Create Date: 2026-06-22 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "20260622_0001"
down_revision = None
branch_labels = None
depends_on = None

MYSQL_TABLE_OPTIONS = {
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_bin",
}


def upgrade() -> None:
    """Create the existing Acquire MySQL schema."""
    op.create_table(
        "game_mode",
        sa.Column("game_mode_id", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("name", sa.String(length=8), nullable=False),
        sa.PrimaryKeyConstraint("game_mode_id"),
        sa.UniqueConstraint("name"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_table(
        "game_state",
        sa.Column("game_state_id", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("game_state_id"),
        sa.UniqueConstraint("name"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_table(
        "key_value",
        sa.Column("key_value_id", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key_value_id"),
        sa.UniqueConstraint("key"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_table(
        "rating_type",
        sa.Column("rating_type_id", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("name", sa.String(length=8), nullable=False),
        sa.PrimaryKeyConstraint("rating_type_id"),
        sa.UniqueConstraint("name"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_table(
        "user",
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("password", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("name"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_table(
        "game",
        sa.Column("game_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("log_time", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("number", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("begin_time", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("end_time", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("game_state_id", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("game_mode_id", mysql.TINYINT(unsigned=True), nullable=False),
        sa.ForeignKeyConstraint(["game_mode_id"], ["game_mode.game_mode_id"]),
        sa.ForeignKeyConstraint(["game_state_id"], ["game_state.game_state_id"]),
        sa.PrimaryKeyConstraint("game_id"),
        sa.UniqueConstraint("log_time", "number"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("end_time", "game", ["end_time"], unique=False)
    op.create_table(
        "rating",
        sa.Column("rating_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("rating_type_id", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("time", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("mu", mysql.FLOAT(), nullable=False),
        sa.Column("sigma", mysql.FLOAT(), nullable=False),
        sa.ForeignKeyConstraint(["rating_type_id"], ["rating_type.rating_type_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"]),
        sa.PrimaryKeyConstraint("rating_id"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index(
        "user_id_rating_type_id",
        "rating",
        ["user_id", "rating_type_id"],
        unique=False,
    )
    op.create_table(
        "record",
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("encoded", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"]),
        sa.PrimaryKeyConstraint("user_id"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_table(
        "game_player",
        sa.Column("game_player_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("game_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("player_index", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("score", mysql.SMALLINT(unsigned=True), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["game.game_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"]),
        sa.PrimaryKeyConstraint("game_player_id"),
        sa.UniqueConstraint("game_id", "player_index"),
        **MYSQL_TABLE_OPTIONS,
    )


def downgrade() -> None:
    """Drop the existing Acquire MySQL schema."""
    op.drop_table("game_player")
    op.drop_table("record")
    op.drop_table("rating")
    op.drop_table("game")
    op.drop_table("user")
    op.drop_table("rating_type")
    op.drop_table("key_value")
    op.drop_table("game_state")
    op.drop_table("game_mode")
