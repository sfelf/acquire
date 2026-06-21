import auth
import enums
import orm
import pytest
from sqlalchemy.exc import SQLAlchemyError

pytestmark = pytest.mark.unit

PASSWORD_HASH = "a" * 64


class FakeSession:
    def __init__(self):
        self.added = []
        self.flushed = False
        self.rolled_back = False
        self.flush_error = None
        self.query_result = None

    def query(self, entity):
        assert entity is orm.User
        return FakeQuery(self.query_result)

    def add(self, instance):
        self.added.append(instance)

    def flush(self):
        self.flushed = True
        if self.flush_error is not None:
            raise self.flush_error

    def rollback(self):
        self.rolled_back = True


class FakeQuery:
    def __init__(self, result):
        self.result = result
        self.filtered = False

    def filter(self, *criterion):
        assert criterion
        self.filtered = True
        return self

    def one_or_none(self):
        assert self.filtered
        return self.result


def make_user(name="alice", password=None):
    return orm.User(name=name, password=password)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  alice  ", "alice"),
        ("first\n\tsecond", "first second"),
        ("many   spaces", "many spaces"),
    ],
)
def test_normalize_form_value_matches_legacy_whitespace_rules(value, expected):
    assert auth.normalize_form_value(value) == expected


def test_normalize_login_value_rejects_non_string_fields():
    with pytest.raises(TypeError, match="login fields must be strings"):
        auth.normalize_login_value(1)


@pytest.mark.parametrize("username", ["alice", "space name", "~" * 32])
def test_validate_username_accepts_printable_ascii_names(username):
    assert auth.validate_username(username) is None


@pytest.mark.parametrize("username", ["", "a" * 33, "line\nbreak", "punyçode"])
def test_validate_username_rejects_legacy_invalid_names(username):
    assert auth.validate_username(username) is enums.Errors.InvalidUsername


@pytest.mark.parametrize(
    ("error", "expected"),
    [(None, "null"), (enums.Errors.InvalidUsername, "2")],
)
def test_error_response_text_matches_legacy_jsonish_body(error, expected):
    assert auth.error_response_text(error) == expected


def test_get_user_queries_by_username():
    session = FakeSession()
    user = make_user()
    session.query_result = user

    assert auth._get_user(session, "alice") is user


@pytest.mark.parametrize(
    ("version", "username", "password", "expected_error"),
    [
        ("old", "alice", "", enums.Errors.NotUsingLatestVersion),
        ("VERSION", "", "", enums.Errors.InvalidUsername),
        ("VERSION", "punyçode", "", enums.Errors.InvalidUsername),
    ],
)
def test_check_login_rejects_version_and_username_errors(
    version,
    username,
    password,
    expected_error,
):
    result = auth.check_login(
        FakeSession(),
        version=version,
        username=username,
        password=password,
    )

    assert result.error is expected_error
    assert result.username == auth.normalize_form_value(username)
    assert result.password == password


def test_check_login_returns_generic_error_when_lookup_fails():
    def get_user(session, username):
        raise SQLAlchemyError("boom")

    result = auth.check_login(
        FakeSession(),
        version="VERSION",
        username="alice",
        password="",
        get_user=get_user,
    )

    assert result.error is enums.Errors.GenericError
    assert result.username == "alice"


@pytest.mark.parametrize(
    ("user", "password", "expected_error", "replace_existing_user"),
    [
        (None, "", None, False),
        (None, PASSWORD_HASH, enums.Errors.ProvidedPassword, False),
        (make_user(password=None), "", None, False),
        (make_user(password=None), PASSWORD_HASH, enums.Errors.ProvidedPassword, False),
        (make_user(password=PASSWORD_HASH), "", enums.Errors.MissingPassword, False),
        (make_user(password=PASSWORD_HASH), "wrong", enums.Errors.IncorrectPassword, False),
        (make_user(password=PASSWORD_HASH), PASSWORD_HASH, None, True),
    ],
)
def test_check_login_preserves_legacy_password_decisions(
    user,
    password,
    expected_error,
    replace_existing_user,
):
    def get_user(session, username):
        return user

    result = auth.check_login(
        FakeSession(),
        version="  VERSION ",
        username=" alice ",
        password=password,
        get_user=get_user,
    )

    assert result.error is expected_error
    assert result.username == "alice"
    assert result.password == password
    assert result.replace_existing_user is replace_existing_user


@pytest.mark.parametrize(
    ("version", "username", "password", "expected_error"),
    [
        ("old", "alice", PASSWORD_HASH, enums.Errors.NotUsingLatestVersion),
        ("VERSION", "", PASSWORD_HASH, enums.Errors.InvalidUsername),
        ("VERSION", "punyçode", PASSWORD_HASH, enums.Errors.InvalidUsername),
        ("VERSION", "alice", "A" * 64, enums.Errors.GenericError),
        ("VERSION", "alice", "short", enums.Errors.GenericError),
        ("VERSION", "alice", "", enums.Errors.GenericError),
    ],
)
def test_set_password_rejects_invalid_inputs(version, username, password, expected_error):
    session = FakeSession()

    result = auth.set_password(
        session,
        version=version,
        username=username,
        password=password,
    )

    assert result is expected_error
    assert session.added == []
    assert session.flushed is False


def test_set_password_creates_missing_user():
    session = FakeSession()

    result = auth.set_password(
        session,
        version=" VERSION ",
        username=" alice ",
        password=PASSWORD_HASH,
        get_user=lambda session, username: None,
    )

    assert result is None
    assert session.flushed is True
    assert len(session.added) == 1
    assert session.added[0].name == "alice"
    assert session.added[0].password == PASSWORD_HASH


def test_set_password_updates_passwordless_user():
    session = FakeSession()
    user = make_user(password=None)

    result = auth.set_password(
        session,
        version="VERSION",
        username="alice",
        password=PASSWORD_HASH,
        get_user=lambda session, username: user,
    )

    assert result is None
    assert user.password == PASSWORD_HASH
    assert session.flushed is True
    assert session.added == []


def test_set_password_rejects_user_with_existing_password():
    session = FakeSession()
    user = make_user(password="b" * 64)

    result = auth.set_password(
        session,
        version="VERSION",
        username="alice",
        password=PASSWORD_HASH,
        get_user=lambda session, username: user,
    )

    assert result is enums.Errors.ExistingPassword
    assert user.password == "b" * 64
    assert session.flushed is False


@pytest.mark.parametrize("failure", ["lookup", "flush"])
def test_set_password_rolls_back_and_returns_generic_error_on_database_errors(failure):
    session = FakeSession()

    def get_user(session, username):
        if failure == "lookup":
            raise SQLAlchemyError("lookup")
        return None

    if failure == "flush":
        session.flush_error = SQLAlchemyError("flush")

    result = auth.set_password(
        session,
        version="VERSION",
        username="alice",
        password=PASSWORD_HASH,
        get_user=get_user,
    )

    assert result is enums.Errors.GenericError
    assert session.rolled_back is True
