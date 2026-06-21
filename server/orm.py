"""Define SQLAlchemy models and lookup helpers for the Acquire database.

This module is part of the legacy Python runtime and replay tooling.
"""

import collections
import os
from contextlib import contextmanager
from typing import cast

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.mysql import FLOAT, INTEGER, SMALLINT, TINYINT
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()
mysql_user = os.environ.get("MYSQL_USER", "acquire")
mysql_password = os.environ.get("MYSQL_PASSWORD", "acquire")
mysql_database = os.environ.get("MYSQL_DATABASE", "acquire")
mysql_socket = os.environ.get("MYSQL_SOCKET", "/var/run/mysqld/mysqld.sock")
mysql_auth_plugin = os.environ.get("MYSQL_AUTH_PLUGIN", "mysql_native_password")
connect_args = {}
if mysql_auth_plugin:
    connect_args["auth_plugin"] = mysql_auth_plugin
engine = create_engine(
    URL(
        "mysql+mysqlconnector",
        username=mysql_user,
        password=mysql_password,
        host="localhost",
        database=mysql_database,
        query={"unix_socket": mysql_socket},
    ),
    connect_args=connect_args,
)
Session = sessionmaker(bind=engine)


@contextmanager
def session_scope():
    """Provide a transactional SQLAlchemy session scope.

    The yielded session is committed when the context exits normally, rolled
    back when any exception escapes, and always closed. Callers should let
    exceptions propagate if they want the transaction rolled back.

    Yields:
        SQLAlchemy session with autoflush disabled.
    """
    session = Session(autoflush=False)
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


class Game(Base):
    """Hold reconstructed game state while replaying logs."""

    __tablename__ = "game"
    game_id = Column(INTEGER(unsigned=True), primary_key=True, nullable=False)
    log_time = Column(INTEGER(unsigned=True), nullable=False)
    number = Column(INTEGER(unsigned=True), nullable=False)
    begin_time = Column(INTEGER(unsigned=True))
    end_time = Column(INTEGER(unsigned=True))
    game_state_id = Column(
        TINYINT(unsigned=True), ForeignKey("game_state.game_state_id"), nullable=False
    )
    game_mode_id = Column(
        TINYINT(unsigned=True), ForeignKey("game_mode.game_mode_id"), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("log_time", "number"),
        Index("end_time", "end_time"),
    )

    game_state = relationship("GameState")
    game_mode = relationship("GameMode")

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (
            repr(self.game_id),
            repr(self.log_time),
            repr(self.number),
            repr(self.begin_time),
            repr(self.end_time),
            repr(self.game_state_id),
            repr(self.game_mode_id),
        )
        return (
            "Game(game_id={}, log_time={}, number={}, begin_time={}, end_time={}, "
            "game_state_id={}, game_mode_id={})".format(*params)
        )


class GameMode(Base):
    """Represent a game mode lookup row."""

    __tablename__ = "game_mode"
    game_mode_id = Column(TINYINT(unsigned=True), primary_key=True, nullable=False)
    name = Column(String(8, convert_unicode="force"), nullable=False)
    __table_args__ = (UniqueConstraint("name"),)

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (repr(self.game_mode_id), repr(self.name))
        return "GameMode(game_mode_id={}, name={})".format(*params)


class GamePlayer(Base):
    """Represent a player entry for a persisted game."""

    __tablename__ = "game_player"
    game_player_id = Column(INTEGER(unsigned=True), primary_key=True, nullable=False)
    game_id = Column(INTEGER(unsigned=True), ForeignKey("game.game_id"), nullable=False)
    player_index = Column(TINYINT(unsigned=True), nullable=False)
    user_id = Column(INTEGER(unsigned=True), ForeignKey("user.user_id"), nullable=False)
    score = Column(SMALLINT(unsigned=True))
    __table_args__ = (UniqueConstraint("game_id", "player_index"),)

    game = relationship("Game")
    user = relationship("User")

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (
            repr(self.game_player_id),
            repr(self.game_id),
            repr(self.player_index),
            repr(self.user_id),
            repr(self.score),
        )
        return (
            "GamePlayer(game_player_id={}, game_id={}, player_index={}, user_id={}, "
            "score={})".format(*params)
        )


class GameState(Base):
    """Represent a game state lookup row."""

    __tablename__ = "game_state"
    game_state_id = Column(TINYINT(unsigned=True), primary_key=True, nullable=False)
    name = Column(String(16, convert_unicode="force"), nullable=False)
    __table_args__ = (UniqueConstraint("name"),)

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (repr(self.game_state_id), repr(self.name))
        return "GameState(game_state_id={}, name={})".format(*params)


class KeyValue(Base):
    """Represent a persisted string key/value pair."""

    __tablename__ = "key_value"
    key_value_id = Column(TINYINT(unsigned=True), primary_key=True, nullable=False)
    key = Column(String(32, convert_unicode="force"), nullable=False)
    value = Column(Text(convert_unicode="force"), nullable=False)
    __table_args__ = (UniqueConstraint("key"),)

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (repr(self.key_value_id), repr(self.key), repr(self.value))
        return "KeyValue(key_value_id={}, key={}, value={})".format(*params)


class Rating(Base):
    """Represent one user rating at a point in time."""

    __tablename__ = "rating"
    rating_id = Column(INTEGER(unsigned=True), primary_key=True, nullable=False)
    user_id = Column(INTEGER(unsigned=True), ForeignKey("user.user_id"), nullable=False)
    rating_type_id = Column(
        TINYINT(unsigned=True), ForeignKey("rating_type.rating_type_id"), nullable=False
    )
    time = Column(INTEGER(unsigned=True), nullable=False)
    mu = Column(FLOAT(), nullable=False)
    sigma = Column(FLOAT(), nullable=False)
    __table_args__ = (Index("user_id_rating_type_id", "user_id", "rating_type_id"),)

    user = relationship("User")
    rating_type = relationship("RatingType")

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (
            repr(self.rating_id),
            repr(self.user_id),
            repr(self.rating_type_id),
            repr(self.time),
            repr(self.mu),
            repr(self.sigma),
        )
        return (
            "Rating(rating_id={}, user_id={}, rating_type_id={}, time={}, mu={}, sigma={})".format(
                *params
            )
        )


class RatingType(Base):
    """Represent a rating category lookup row."""

    __tablename__ = "rating_type"
    rating_type_id = Column(TINYINT(unsigned=True), primary_key=True, nullable=False)
    name = Column(String(8, convert_unicode="force"), nullable=False)
    __table_args__ = (UniqueConstraint("name"),)

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (repr(self.rating_type_id), repr(self.name))
        return "RatingType(rating_type_id={}, name={})".format(*params)


class Record(Base):
    """Represent encoded per-user stats records."""

    __tablename__ = "record"
    user_id = Column(
        INTEGER(unsigned=True),
        ForeignKey("user.user_id"),
        primary_key=True,
        nullable=False,
    )
    encoded = Column(String(255, convert_unicode="force"), nullable=False)

    user = relationship("User")

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (
            repr(self.user_id),
            repr(self.encoded),
        )
        return "Record(user_id={}, encoded={})".format(*params)


class User(Base):
    """Represent a persisted player account."""

    __tablename__ = "user"
    user_id = Column(INTEGER(unsigned=True), primary_key=True, nullable=False)
    name = Column(String(32, convert_unicode="force"), nullable=False)
    password = Column(String(64, convert_unicode="force"))
    __table_args__ = (UniqueConstraint("name"),)

    def __repr__(self) -> str:
        """Return a stable developer representation for debugging.

        Returns:
            Stable debug string for the ORM row.
        """
        params = (repr(self.user_id), repr(self.name), repr(self.password))
        return "User(user_id={}, name={}, password={})".format(*params)


class Lookup:
    """Cache ORM lookups while importing logs.

    The import path repeatedly resolves games, users, ratings, and lookup rows
    from historical log records. This object keeps per-session caches and also
    creates missing mutable rows, so callers must use it with the session that
    should own any newly added ORM objects.
    """

    def __init__(self, session):
        """Initialize lookup caches for a database session.

        Args:
            session: SQLAlchemy session used for all queries and new ORM rows.
        """
        self.session = session
        self.game_lookup: collections.defaultdict[int, dict[int, Game]] = collections.defaultdict(
            dict
        )
        self.game_mode_lookup: dict[str, GameMode | None] = {}
        self.game_player_lookup: collections.defaultdict[
            int, collections.defaultdict[int, dict[int, GamePlayer]]
        ] = collections.defaultdict(lambda: collections.defaultdict(dict))
        self.game_state_lookup: dict[str, GameState | None] = {}
        self.key_value_lookup: dict[str, KeyValue] = {}
        self.rating_lookup: collections.defaultdict[str, dict[str, Rating]] = (
            collections.defaultdict(dict)
        )
        self.rating_type_lookup: dict[str, RatingType | None] = {}
        self.record_lookup: dict[str, Record] = {}
        self.user_lookup: dict[str, User] = {}

    def get_game(self, log_time: int, number: int) -> Game:
        """Return the persisted or newly added game for a log identity.

        A `(log_time, number)` pair is the stable identity used by historical
        logs. Missing games are added to the session but are not committed here.

        Args:
            log_time: Timestamp identifying the source log file.
            number: Internal game number within the log.

        Returns:
            Existing or newly added `Game` ORM object.
        """
        game = self.game_lookup[log_time].get(number, None)
        if game:
            return game

        game = cast(
            Game | None,
            self.session.query(Game).filter_by(log_time=log_time, number=number).scalar(),
        )
        if not game:
            game = Game(log_time=log_time, number=number)
            self.session.add(game)

        self.game_lookup[log_time][number] = game
        return game

    def get_game_mode(self, name: str) -> GameMode | None:
        """Return the game mode lookup row for a mode name.

        Args:
            name: Persisted mode name such as `Singles` or `Teams`.

        Returns:
            Matching `GameMode` row, or `None` when the lookup table is missing it.
        """
        game_mode = self.game_mode_lookup.get(name, None)
        if game_mode:
            return game_mode

        game_mode = cast(
            GameMode | None, self.session.query(GameMode).filter_by(name=name).scalar()
        )

        self.game_mode_lookup[name] = game_mode
        return game_mode

    def get_game_player(self, game: Game, player_index: int) -> GamePlayer:
        """Return the player row for a game seat.

        Persisted games are queried by database id; unsaved games use the
        in-memory game relationship. Missing rows are added to the session so
        log import can attach user and score data incrementally.

        Args:
            game: Game ORM object that owns the player row.
            player_index: Seat index from the historical log.

        Returns:
            Existing or newly added `GamePlayer` ORM object.
        """
        game_player = self.game_player_lookup[game.log_time][game.number].get(player_index, None)
        if game_player:
            return game_player

        if game.game_id:
            game_player = cast(
                GamePlayer | None,
                self.session.query(GamePlayer)
                .filter_by(game_id=game.game_id, player_index=player_index)
                .scalar(),
            )

        if not game_player:
            game_player = GamePlayer(game=game, player_index=player_index)
            self.session.add(game_player)

        self.game_player_lookup[game.log_time][game.number][player_index] = game_player
        return game_player

    def get_game_state(self, name: str) -> GameState | None:
        """Return the game state lookup row for a state name.

        Args:
            name: Persisted state name from the log.

        Returns:
            Matching `GameState` row, or `None` when the lookup table is missing it.
        """
        game_state = self.game_state_lookup.get(name, None)
        if game_state:
            return game_state

        game_state = cast(
            GameState | None, self.session.query(GameState).filter_by(name=name).scalar()
        )

        self.game_state_lookup[name] = game_state
        return game_state

    def get_key_value(self, key: str) -> KeyValue:
        """Return a mutable key/value row, creating it when absent.

        Cron import stores progress offsets in this table. New rows are added to
        the session with only the key populated, so callers are responsible for
        assigning the value before commit when needed.

        Args:
            key: Stable key name to look up.

        Returns:
            Existing or newly added `KeyValue` ORM object.
        """
        key_value = self.key_value_lookup.get(key, None)
        if key_value:
            return key_value

        key_value = cast(KeyValue | None, self.session.query(KeyValue).filter_by(key=key).scalar())
        if not key_value:
            key_value = KeyValue(key=key)
            self.session.add(key_value)

        self.key_value_lookup[key] = key_value
        return key_value

    def get_rating(self, user: User, rating_type: RatingType) -> Rating | None:
        """Return the latest persisted rating for a user and rating type.

        Unsaved users cannot have persisted ratings, so this returns `None`
        until the user has a database id. Unlike `get_game`, this does not
        create a missing rating row.

        Args:
            user: User ORM object whose rating should be found.
            rating_type: Rating type ORM object to search within.

        Returns:
            Latest matching `Rating`, or `None` when none exists.
        """
        rating = self.rating_lookup[user.name].get(rating_type.name, None)
        if rating:
            return rating

        if user.user_id:
            rating = cast(
                Rating | None,
                self.session.query(Rating)
                .filter_by(user=user, rating_type=rating_type)
                .order_by(Rating.rating_id.desc())
                .limit(1)
                .scalar(),
            )

        if rating:
            self.rating_lookup[user.name][rating_type.name] = rating

        return rating

    def add_rating(self, rating: Rating) -> None:
        """Cache a newly created rating as the latest known rating.

        Args:
            rating: Rating ORM object already associated with a user and type.
        """
        self.rating_lookup[rating.user.name][rating.rating_type.name] = rating

    def get_rating_type(self, name: str) -> RatingType | None:
        """Return the rating type lookup row for a name.

        Args:
            name: Rating type name such as `Singles2` or `Teams`.

        Returns:
            Matching `RatingType` row, or `None` when the lookup table is missing it.
        """
        rating_type = self.rating_type_lookup.get(name, None)
        if rating_type:
            return rating_type

        rating_type = cast(
            RatingType | None, self.session.query(RatingType).filter_by(name=name).scalar()
        )

        self.rating_type_lookup[name] = rating_type
        return rating_type

    def get_record(self, user: User) -> Record | None:
        """Return the encoded stats record for a persisted user.

        Unsaved users cannot have records, so this returns `None` until the user
        has a database id. Missing records are not created here because callers
        need to decide the initial encoded payload.

        Args:
            user: User ORM object whose record should be found.

        Returns:
            Matching `Record`, or `None` when no record exists.
        """
        record = self.record_lookup.get(user.name, None)
        if record:
            return record

        if user.user_id:
            record = cast(
                Record | None, self.session.query(Record).filter_by(user=user).limit(1).scalar()
            )

        if record:
            self.record_lookup[user.name] = record

        return record

    def add_record(self, record: Record) -> None:
        """Cache a newly created stats record.

        Args:
            record: Record ORM object already associated with a user.
        """
        self.record_lookup[record.user.name] = record

    def get_user(self, name: str) -> User:
        """Return the persisted or newly added user for a username.

        Missing users are added to the session with no password because log
        import can encounter historical players that do not yet exist locally.

        Args:
            name: Username from a log record.

        Returns:
            Existing or newly added `User` ORM object.
        """
        user = self.user_lookup.get(name, None)
        if user:
            return user

        user = cast(User | None, self.session.query(User).filter_by(name=name).scalar())
        if not user:
            user = User(name=name)
            self.session.add(user)

        self.user_lookup[name] = user
        return user
