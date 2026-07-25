"""Define the isolated legacy-source and current-target migration schemas.

The backup importer deliberately owns these table definitions instead of
importing :mod:`acquire.orm`. This keeps migration-module loading from creating
the application engine and prevents future runtime-model refactors from
silently changing the supported legacy backup contract.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.sql.schema import Table


def _legacy_unsigned_integer() -> sa.BigInteger:
    """Return the historical unsigned integer type with a portable fallback."""
    return sa.BigInteger().with_variant(mysql.INTEGER(unsigned=True), "mysql")


def _legacy_unsigned_small_integer() -> sa.Integer:
    """Return the historical unsigned small-integer type."""
    return sa.Integer().with_variant(mysql.SMALLINT(unsigned=True), "mysql")


def _legacy_unsigned_tiny_integer() -> sa.SmallInteger:
    """Return the historical unsigned tiny-integer type."""
    return sa.SmallInteger().with_variant(mysql.TINYINT(unsigned=True), "mysql")


def _legacy_float() -> sa.Float:
    """Return the historical MySQL float type with a portable fallback."""
    return sa.Float().with_variant(mysql.FLOAT(), "mysql")


def _target_float() -> sa.Float:
    """Return the current Postgres-compatible rating float type."""
    return sa.Float().with_variant(postgresql.REAL(), "postgresql")


LEGACY_SOURCE_METADATA = sa.MetaData()

sa.Table(
    "game_mode",
    LEGACY_SOURCE_METADATA,
    sa.Column("game_mode_id", _legacy_unsigned_tiny_integer(), primary_key=True),
    sa.Column("name", sa.String(8), nullable=False, unique=True),
)
sa.Table(
    "game_state",
    LEGACY_SOURCE_METADATA,
    sa.Column("game_state_id", _legacy_unsigned_tiny_integer(), primary_key=True),
    sa.Column("name", sa.String(16), nullable=False, unique=True),
)
sa.Table(
    "rating_type",
    LEGACY_SOURCE_METADATA,
    sa.Column("rating_type_id", _legacy_unsigned_tiny_integer(), primary_key=True),
    sa.Column("name", sa.String(8), nullable=False, unique=True),
)
sa.Table(
    "user",
    LEGACY_SOURCE_METADATA,
    sa.Column("user_id", _legacy_unsigned_integer(), primary_key=True),
    sa.Column("name", sa.String(32), nullable=False, unique=True),
    sa.Column("password", sa.String(64)),
)
sa.Table(
    "game",
    LEGACY_SOURCE_METADATA,
    sa.Column("game_id", _legacy_unsigned_integer(), primary_key=True),
    sa.Column("log_time", _legacy_unsigned_integer(), nullable=False),
    sa.Column("number", _legacy_unsigned_integer(), nullable=False),
    sa.Column("begin_time", _legacy_unsigned_integer()),
    sa.Column("end_time", _legacy_unsigned_integer()),
    sa.Column(
        "game_state_id",
        _legacy_unsigned_tiny_integer(),
        sa.ForeignKey("game_state.game_state_id"),
        nullable=False,
    ),
    sa.Column(
        "game_mode_id",
        _legacy_unsigned_tiny_integer(),
        sa.ForeignKey("game_mode.game_mode_id"),
        nullable=False,
    ),
    sa.UniqueConstraint("log_time", "number"),
)
sa.Table(
    "game_player",
    LEGACY_SOURCE_METADATA,
    sa.Column("game_player_id", _legacy_unsigned_integer(), primary_key=True),
    sa.Column(
        "game_id",
        _legacy_unsigned_integer(),
        sa.ForeignKey("game.game_id"),
        nullable=False,
    ),
    sa.Column("player_index", _legacy_unsigned_tiny_integer(), nullable=False),
    sa.Column(
        "user_id",
        _legacy_unsigned_integer(),
        sa.ForeignKey("user.user_id"),
        nullable=False,
    ),
    sa.Column("score", _legacy_unsigned_small_integer()),
    sa.UniqueConstraint("game_id", "player_index"),
)
sa.Table(
    "key_value",
    LEGACY_SOURCE_METADATA,
    sa.Column("key_value_id", _legacy_unsigned_tiny_integer(), primary_key=True),
    sa.Column("key", sa.String(32), nullable=False, unique=True),
    sa.Column("value", sa.Text(), nullable=False),
)
sa.Table(
    "rating",
    LEGACY_SOURCE_METADATA,
    sa.Column("rating_id", _legacy_unsigned_integer(), primary_key=True),
    sa.Column(
        "user_id",
        _legacy_unsigned_integer(),
        sa.ForeignKey("user.user_id"),
        nullable=False,
    ),
    sa.Column(
        "rating_type_id",
        _legacy_unsigned_tiny_integer(),
        sa.ForeignKey("rating_type.rating_type_id"),
        nullable=False,
    ),
    sa.Column("time", _legacy_unsigned_integer(), nullable=False),
    sa.Column("mu", _legacy_float(), nullable=False),
    sa.Column("sigma", _legacy_float(), nullable=False),
)
sa.Table(
    "record",
    LEGACY_SOURCE_METADATA,
    sa.Column(
        "user_id",
        _legacy_unsigned_integer(),
        sa.ForeignKey("user.user_id"),
        primary_key=True,
    ),
    sa.Column("encoded", sa.String(255), nullable=False),
)

LEGACY_SOURCE_TABLES: dict[str, Table] = dict(LEGACY_SOURCE_METADATA.tables)


CURRENT_TARGET_METADATA = sa.MetaData()

sa.Table(
    "game_mode",
    CURRENT_TARGET_METADATA,
    sa.Column("game_mode_id", sa.SmallInteger(), primary_key=True),
    sa.Column("name", sa.String(8), nullable=False, unique=True),
)
sa.Table(
    "game_state",
    CURRENT_TARGET_METADATA,
    sa.Column("game_state_id", sa.SmallInteger(), primary_key=True),
    sa.Column("name", sa.String(16), nullable=False, unique=True),
)
sa.Table(
    "rating_type",
    CURRENT_TARGET_METADATA,
    sa.Column("rating_type_id", sa.SmallInteger(), primary_key=True),
    sa.Column("name", sa.String(8), nullable=False, unique=True),
)
sa.Table(
    "user",
    CURRENT_TARGET_METADATA,
    sa.Column("user_id", sa.BigInteger(), primary_key=True),
    sa.Column("name", sa.String(32), nullable=False, unique=True),
    sa.Column("password", sa.String(64)),
)
sa.Table(
    "game",
    CURRENT_TARGET_METADATA,
    sa.Column("game_id", sa.BigInteger(), primary_key=True),
    sa.Column("log_time", sa.BigInteger(), nullable=False),
    sa.Column("number", sa.BigInteger(), nullable=False),
    sa.Column("begin_time", sa.BigInteger()),
    sa.Column("end_time", sa.BigInteger()),
    sa.Column(
        "game_state_id",
        sa.SmallInteger(),
        sa.ForeignKey("game_state.game_state_id"),
        nullable=False,
    ),
    sa.Column(
        "game_mode_id",
        sa.SmallInteger(),
        sa.ForeignKey("game_mode.game_mode_id"),
        nullable=False,
    ),
    sa.UniqueConstraint("log_time", "number"),
)
sa.Table(
    "game_player",
    CURRENT_TARGET_METADATA,
    sa.Column("game_player_id", sa.BigInteger(), primary_key=True),
    sa.Column("game_id", sa.BigInteger(), sa.ForeignKey("game.game_id"), nullable=False),
    sa.Column("player_index", sa.SmallInteger(), nullable=False),
    sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("user.user_id"), nullable=False),
    sa.Column("score", sa.Integer()),
    sa.UniqueConstraint("game_id", "player_index"),
)
sa.Table(
    "key_value",
    CURRENT_TARGET_METADATA,
    sa.Column("key_value_id", sa.SmallInteger(), primary_key=True),
    sa.Column("key", sa.String(32), nullable=False, unique=True),
    sa.Column("value", sa.Text(), nullable=False),
)
sa.Table(
    "rating",
    CURRENT_TARGET_METADATA,
    sa.Column("rating_id", sa.BigInteger(), primary_key=True),
    sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("user.user_id"), nullable=False),
    sa.Column(
        "rating_type_id",
        sa.SmallInteger(),
        sa.ForeignKey("rating_type.rating_type_id"),
        nullable=False,
    ),
    sa.Column("time", sa.BigInteger(), nullable=False),
    sa.Column("mu", _target_float(), nullable=False),
    sa.Column("sigma", _target_float(), nullable=False),
)
sa.Table(
    "record",
    CURRENT_TARGET_METADATA,
    sa.Column(
        "user_id",
        sa.BigInteger(),
        sa.ForeignKey("user.user_id"),
        primary_key=True,
    ),
    sa.Column("encoded", sa.String(255), nullable=False),
)

CURRENT_TARGET_TABLES: dict[str, Table] = dict(CURRENT_TARGET_METADATA.tables)
