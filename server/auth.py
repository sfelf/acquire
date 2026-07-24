"""Implement legacy-compatible authentication and password rules.

The removed Node gateway used these rules for login validation and
`/server/set-password`. The Python HTTP and websocket gateway share this
behavior-preserving implementation so the client contract stays stable while
the backend is refactored.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable
from typing import Protocol

import orm
from sqlalchemy.exc import SQLAlchemyError

from acquire import enums

PASSWORD_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class UserQuery(Protocol):
    """Represent the SQLAlchemy query operations needed for user lookup."""

    def filter(self, *criterion: object) -> UserQuery:
        """Apply lookup criteria to the user query.

        Args:
            *criterion: SQLAlchemy filter expressions.

        Returns:
            Query narrowed by the supplied criteria.
        """

    def one_or_none(self) -> orm.User | None:
        """Return a single user row or no row.

        Returns:
            Matching user row, or `None` when no user exists.
        """


class AuthSession(Protocol):
    """Represent the SQLAlchemy session operations needed by auth checks."""

    def query(self, entity: type[orm.User]) -> UserQuery:
        """Start a query for user rows.

        Args:
            entity: ORM user model class.

        Returns:
            Query object for user rows.
        """

    def add(self, instance: object) -> None:
        """Add a new ORM row to the current transaction.

        Args:
            instance: ORM model instance to persist.
        """

    def flush(self) -> None:
        """Flush pending auth changes to the database."""

    def rollback(self) -> None:
        """Roll back pending auth changes after a database error."""


@dataclasses.dataclass(frozen=True)
class LoginResult:
    """Describe the result of a legacy SockJS login check.

    Login does not create missing users. A successful password-authenticated
    login asks the Python server to replace an already connected username,
    while successful passwordless login does not.

    Attributes:
        error: Client-visible fatal error, or `None` when login may continue.
        username: Normalized username to pass to the Python game server.
        password: Normalized password supplied by the client.
        replace_existing_user: Whether a successful login should replace an
            already connected client with the same username.
    """

    error: enums.Errors | None
    username: str = ""
    password: str = ""
    replace_existing_user: bool = False


def normalize_form_value(value: str | None) -> str:
    r"""Collapse and trim whitespace in a submitted form value.

    Args:
        value: Submitted string value, or `None` when the field is absent.

    Returns:
        Normalized value matching the legacy JavaScript `replace(/\s+/g, " ").trim()`.
    """
    if value is None:
        return ""
    return " ".join(value.split())


def normalize_login_value(value: object) -> str:
    """Collapse and trim whitespace in a login tuple value.

    The removed Node gateway called `.replace()` on each login tuple field.
    Non-string values therefore raise and cause the socket to close without a
    fatal error.

    Args:
        value: Login tuple field supplied by the client.

    Returns:
        Normalized string value.

    Raises:
        TypeError: If the value is not a string.
    """
    if not isinstance(value, str):
        raise TypeError("login fields must be strings")
    return normalize_form_value(value)


def is_ascii_username(username: str) -> bool:
    """Return whether a username matches the legacy printable ASCII range.

    Args:
        username: Normalized username.

    Returns:
        `True` when every character is between ASCII 32 and 126 inclusive.
    """
    return all(32 <= ord(character) <= 126 for character in username)


def validate_username(username: str) -> enums.Errors | None:
    """Validate a normalized username.

    Args:
        username: Normalized username.

    Returns:
        Legacy error value, or `None` when valid.
    """
    if len(username) < 1 or len(username) > 32 or not is_ascii_username(username):
        return enums.Errors.InvalidUsername
    return None


def error_response_text(error: enums.Errors | None) -> str:
    """Return the legacy string body for an error result.

    Args:
        error: Error enum or `None` for success.

    Returns:
        `"null"` on success, otherwise the numeric enum value as a string.
    """
    return "null" if error is None else str(error.value)


def _get_user(session: AuthSession, username: str) -> orm.User | None:
    """Return the persisted user for a username.

    Args:
        session: SQLAlchemy session.
        username: Normalized username.

    Returns:
        Matching user row, or `None`.
    """
    return session.query(orm.User).filter(orm.User.name == username).one_or_none()


def check_login(
    session: AuthSession,
    *,
    version: object,
    username: object,
    password: object,
    server_version: str = "VERSION",
    get_user: Callable[[AuthSession, str], orm.User | None] = _get_user,
) -> LoginResult:
    """Validate a legacy SockJS login tuple.

    This preserves the removed Node gateway's behavior: malformed non-string fields
    raise before a fatal error can be sent, missing users may log in only with an
    empty password and are not created, and login password strings are compared
    as-is without hash-format validation.

    Args:
        session: SQLAlchemy session used for user lookup.
        version: Client version tuple field.
        username: Username tuple field.
        password: Password tuple field.
        server_version: Accepted client version token.
        get_user: User lookup function, injectable for tests.

    Returns:
        Login result describing any fatal error and normalized successful values.

    Raises:
        TypeError: If any login tuple field is not a string.
    """
    normalized_version = normalize_login_value(version)
    normalized_username = normalize_login_value(username)
    normalized_password = normalize_login_value(password)

    if normalized_version != server_version:
        return LoginResult(
            enums.Errors.NotUsingLatestVersion,
            normalized_username,
            normalized_password,
        )

    username_error = validate_username(normalized_username)
    if username_error is not None:
        return LoginResult(username_error, normalized_username, normalized_password)

    try:
        user = get_user(session, normalized_username)
    except SQLAlchemyError:
        return LoginResult(
            enums.Errors.GenericError,
            normalized_username,
            normalized_password,
        )

    if user is None:
        if normalized_password:
            return LoginResult(
                enums.Errors.ProvidedPassword,
                normalized_username,
                normalized_password,
            )
        return LoginResult(None, normalized_username, normalized_password)

    if user.password is None:
        if normalized_password:
            return LoginResult(
                enums.Errors.ProvidedPassword,
                normalized_username,
                normalized_password,
            )
        return LoginResult(None, normalized_username, normalized_password)

    if not normalized_password:
        return LoginResult(enums.Errors.MissingPassword, normalized_username, normalized_password)
    if normalized_password != user.password:
        return LoginResult(enums.Errors.IncorrectPassword, normalized_username, normalized_password)
    return LoginResult(
        None,
        normalized_username,
        normalized_password,
        replace_existing_user=True,
    )


def set_password(
    session: AuthSession,
    *,
    version: str | None,
    username: str | None,
    password: str | None,
    server_version: str = "VERSION",
    get_user: Callable[[AuthSession, str], orm.User | None] = _get_user,
) -> enums.Errors | None:
    """Set or create a user password using legacy `/server/set-password` rules.

    This function flushes database writes before returning so insert/update
    errors are reported as `Errors.GenericError`, matching the Node callback
    behavior before the HTTP response is sent.

    Args:
        session: SQLAlchemy session used for lookup and persistence.
        version: Submitted client version field.
        username: Submitted username field.
        password: Submitted password hash field.
        server_version: Accepted client version token.
        get_user: User lookup function, injectable for tests.

    Returns:
        Legacy error value, or `None` when the password was set or user created.
    """
    normalized_version = normalize_form_value(version)
    normalized_username = normalize_form_value(username)
    normalized_password = normalize_form_value(password)

    if normalized_version != server_version:
        return enums.Errors.NotUsingLatestVersion

    username_error = validate_username(normalized_username)
    if username_error is not None:
        return username_error

    if PASSWORD_HASH_RE.fullmatch(normalized_password) is None:
        return enums.Errors.GenericError

    try:
        user = get_user(session, normalized_username)
        if user is None:
            session.add(orm.User(name=normalized_username, password=normalized_password))
        elif user.password is None:
            user.password = normalized_password
        else:
            return enums.Errors.ExistingPassword
        session.flush()
    except SQLAlchemyError:
        session.rollback()
        return enums.Errors.GenericError

    return None
