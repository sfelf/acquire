import io
import time
import urllib.parse
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from acquire import enums, http_server

pytestmark = pytest.mark.unit


def make_client(
    tmp_path,
    *,
    log_output=None,
    session_scope=None,
    accepted_client_version="VERSION",
    realtime_gateway=None,
    sockjs_heartbeat_interval=60,
    expired_game_cleanup_interval=60,
):
    main_root = tmp_path / "main"
    stats_root = tmp_path / "stats"
    main_root.mkdir(exist_ok=True)
    stats_root.mkdir(exist_ok=True)
    app = http_server.create_app(
        main_static_root=main_root,
        stats_static_root=stats_root,
        log_output=log_output or io.StringIO(),
        session_scope=session_scope or (lambda: fake_session_scope(object())),
        accepted_client_version=accepted_client_version,
        realtime_gateway=realtime_gateway,
        sockjs_heartbeat_interval=sockjs_heartbeat_interval,
        expired_game_cleanup_interval=expired_game_cleanup_interval,
    )
    return TestClient(app), main_root, stats_root


def decode_sockjs_messages(frame):
    assert frame[0] == "a"
    messages = []
    for item in http_server.ujson.loads(frame[1:]):
        decoded = http_server.ujson.loads(item)
        if decoded and isinstance(decoded[0], list):
            messages.extend(decoded)
        else:
            messages.append(decoded)
    return messages


def encode_sockjs_message(message):
    return http_server.ujson.dumps([http_server.ujson.dumps(message)])


def receive_next_sockjs_message_frame(websocket):
    while True:
        frame = websocket.receive_text()
        if frame != "h":
            return frame


@contextmanager
def fake_session_scope(session):
    yield session


class RollbackTrackingSession:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


def test_python_http_server_serves_main_static_assets(tmp_path):
    client, main_root, _stats_root = make_client(tmp_path)
    (main_root / "css").mkdir()
    (main_root / "index.html").write_text("<h1>Acquire</h1>", encoding="utf-8")
    (main_root / "css" / "main.css").write_text(
        "body { color: black; }",
        encoding="utf-8",
    )

    index_response = client.get("/")
    css_response = client.get("/css/main.css")

    assert index_response.status_code == 200
    assert index_response.headers["content-type"].startswith("text/html")
    assert index_response.content == b"<h1>Acquire</h1>"
    assert css_response.status_code == 200
    assert css_response.headers["content-type"].startswith("text/css")
    assert css_response.content == b"body { color: black; }"


def test_python_http_server_serves_stats_static_assets(tmp_path):
    client, _main_root, stats_root = make_client(tmp_path)
    (stats_root / "js").mkdir()
    (stats_root / "index.html").write_text(
        "<h1>Acquire stats</h1>",
        encoding="utf-8",
    )
    (stats_root / "js" / "stats.js").write_text(
        "window.stats = true;",
        encoding="utf-8",
    )

    index_response = client.get("/stats/")
    js_response = client.get("/stats/js/stats.js")

    assert index_response.status_code == 200
    assert index_response.headers["content-type"].startswith("text/html")
    assert index_response.content == b"<h1>Acquire stats</h1>"
    assert js_response.status_code == 200
    assert js_response.headers["content-type"].startswith("text/javascript")
    assert js_response.content == b"window.stats = true;"


def test_python_http_server_serves_cron_generated_stats_data(tmp_path):
    client, _main_root, stats_root = make_client(tmp_path)
    users_root = stats_root / "data" / "users"
    users_root.mkdir(parents=True)
    (stats_root / "data" / "ratings.json").write_text(
        '{"Singles2":[]}',
        encoding="utf-8",
    )
    (users_root / "alice.json").write_text(
        '{"username":"alice"}',
        encoding="utf-8",
    )

    ratings_response = client.get("/stats/data/ratings.json")
    user_response = client.get("/stats/data/users/alice.json")

    assert ratings_response.status_code == 200
    assert ratings_response.headers["content-type"].startswith("application/json")
    assert ratings_response.json() == {"Singles2": []}
    assert user_response.status_code == 200
    assert user_response.headers["content-type"].startswith("application/json")
    assert user_response.json() == {"username": "alice"}


def test_python_http_server_redirects_stats_index_without_trailing_slash(tmp_path):
    client, _main_root, stats_root = make_client(tmp_path)
    (stats_root / "index.html").write_text(
        "<h1>Acquire stats</h1>",
        encoding="utf-8",
    )

    response = client.get("/stats", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/stats/"
    assert response.content == b""


def test_python_http_server_redirects_stats_query_to_slash_path(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)

    response = client.get("/stats?ratings=singles", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/stats/?ratings=singles"


def test_python_http_server_redirects_stats_head_requests(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)

    response = client.head("/stats", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/stats/"
    assert response.content == b""


def test_python_http_server_rejects_path_traversal(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)
    (tmp_path / "secret.txt").write_text("hidden", encoding="utf-8")

    response = client.get("/../secret.txt")

    assert response.status_code == 404


def test_python_http_server_does_not_expose_openapi_schema(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 404


def test_safe_join_normalizes_empty_paths_to_index(tmp_path):
    root = tmp_path / "main"
    root.mkdir()

    assert http_server.safe_join(root, ".") == (root / "index.html").resolve()


def test_safe_join_rejects_static_root_itself(tmp_path):
    root = tmp_path / "main"
    root.mkdir()

    assert http_server.safe_join(root, "./..") is None


def test_python_http_server_head_sends_headers_without_body(tmp_path):
    client, main_root, _stats_root = make_client(tmp_path)
    (main_root / "index.html").write_text("<h1>Acquire</h1>", encoding="utf-8")

    response = client.head("/")

    assert response.status_code == 200
    assert response.headers["content-length"] == "16"
    assert response.content == b""


def test_python_http_server_accepts_report_error_posts(tmp_path):
    log_output = io.StringIO()
    body = urllib.parse.urlencode(
        {
            "message": "first\nsecond",
            "trace": "trace\nline",
        }
    )
    client, _main_root, _stats_root = make_client(tmp_path, log_output=log_output)

    response = client.post(
        "/server/report-error",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.content == b""
    assert "/server/report-error: first\n\tsecond" in log_output.getvalue()
    assert "\ttrace\n\tline" in log_output.getvalue()


def test_python_http_server_report_error_logs_null_missing_fields(tmp_path):
    log_output = io.StringIO()
    client, _main_root, _stats_root = make_client(tmp_path, log_output=log_output)

    response = client.post("/server/report-error", content=b"")

    assert response.status_code == 200
    assert response.content == b""
    assert "/server/report-error: <null>" in log_output.getvalue()
    assert "\t<null>" in log_output.getvalue()


def test_python_http_server_rejects_oversized_report_error_before_reading(tmp_path):
    log_output = io.StringIO()
    client, _main_root, _stats_root = make_client(tmp_path, log_output=log_output)

    response = client.post(
        "/server/report-error",
        content=b"",
        headers={"Content-Length": str(http_server.MAX_REPORT_ERROR_BODY_BYTES + 1)},
    )

    assert response.status_code == 413
    assert log_output.getvalue() == ""


@pytest.mark.parametrize(("content_length", "status_code"), [("not-a-number", 400), ("-1", 400)])
def test_validate_content_length_rejects_invalid_values(content_length, status_code):
    request = SimpleNamespace(headers={"content-length": content_length})

    with pytest.raises(HTTPException) as exc_info:
        http_server.validate_content_length(request)

    assert exc_info.value.status_code == status_code


def test_validate_content_length_rejects_missing_header_before_body_buffering():
    request = SimpleNamespace(headers={})

    with pytest.raises(HTTPException) as exc_info:
        http_server.validate_content_length(request)

    assert exc_info.value.status_code == 411


def test_python_http_server_rejects_unknown_post_routes(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)

    response = client.post("/server/unknown")

    assert response.status_code == 404


def test_python_http_server_serves_sockjs_info_negotiation_endpoint(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)

    response = client.get("/sockjs/info")

    assert response.status_code == 200
    body = response.json()
    assert body["websocket"] is True
    assert body["origins"] == ["*:*"]
    assert body["cookie_needed"] is False
    assert isinstance(body["entropy"], int)


def test_python_http_server_sockjs_websocket_logs_in_and_receives_initial_state(
    tmp_path, monkeypatch
):
    session = object()

    def check_login(session_arg, **kwargs):
        assert session_arg is session
        assert kwargs == {
            "version": " VERSION ",
            "username": " alice ",
            "password": "",
            "server_version": "VERSION",
        }
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(
        tmp_path,
        session_scope=lambda: fake_session_scope(session),
    )

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket:
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message([" VERSION ", " alice ", ""]))
        messages = decode_sockjs_messages(websocket.receive_text())

    assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in messages
    assert [
        http_server.enums.CommandsToClient.SetClientIdToData.value,
        1,
        "alice",
        None,
    ] in messages


def test_python_http_server_raw_websocket_logs_in_and_receives_unwrapped_messages(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path)

    with client.websocket_connect("/sockjs/websocket") as websocket:
        websocket.send_text(http_server.ujson.dumps(["VERSION", "alice", ""]))
        messages = http_server.ujson.loads(websocket.receive_text())

        websocket.send_text(
            http_server.ujson.dumps(
                [
                    http_server.enums.CommandsToServer.SendGlobalChatMessage.value,
                    "hello from raw websocket",
                ]
            )
        )
        chat_messages = http_server.ujson.loads(websocket.receive_text())

    assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in messages
    assert [
        http_server.enums.CommandsToClient.AddGlobalChatMessage.value,
        1,
        "hello from raw websocket",
    ] in chat_messages


def test_python_http_server_sockjs_websocket_ignores_empty_frames_before_login(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path)

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket:
        assert websocket.receive_text() == "o"
        websocket.send_text("")
        websocket.send_text("h")
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        messages = decode_sockjs_messages(websocket.receive_text())

    assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in messages


def test_python_http_server_sockjs_websocket_sends_idle_heartbeats(tmp_path, monkeypatch):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path, sockjs_heartbeat_interval=0.01)

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket:
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in (
            decode_sockjs_messages(websocket.receive_text())
        )
        assert websocket.receive_text() == "h"


def test_python_http_server_sockjs_websocket_rejects_duplicate_session_ids(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as first_websocket:
        assert first_websocket.receive_text() == "o"
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/sockjs/000/socket-alice/websocket") as second_websocket,
        ):
            assert second_websocket.receive_text() == "o"
            second_websocket.receive_text()


def test_python_http_server_sockjs_websocket_sends_fatal_login_errors(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(
            http_server.enums.Errors.NotUsingLatestVersion,
            "alice",
            "",
        )

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path)

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket:
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["old", "alice", ""]))
        messages = decode_sockjs_messages(websocket.receive_text())

    assert messages == [
        [
            http_server.enums.CommandsToClient.FatalError.value,
            http_server.enums.Errors.NotUsingLatestVersion.value,
        ]
    ]


def test_python_http_server_raw_websocket_sends_unwrapped_fatal_login_errors(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(
            http_server.enums.Errors.NotUsingLatestVersion,
            "alice",
            "",
        )

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path)

    with client.websocket_connect("/sockjs/websocket") as websocket:
        websocket.send_text(http_server.ujson.dumps(["old", "alice", ""]))
        messages = http_server.ujson.loads(websocket.receive_text())

    assert messages == [
        [
            http_server.enums.CommandsToClient.FatalError.value,
            http_server.enums.Errors.NotUsingLatestVersion.value,
        ]
    ]


def test_python_http_server_sockjs_websocket_closes_malformed_login_payload(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket,
    ):
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice"]))
        websocket.receive_text()


def test_decode_login_payload_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid login payload JSON"):
        http_server.decode_login_payload("not json")


def test_python_http_server_sockjs_websocket_drops_extra_first_frame_messages(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path, sockjs_heartbeat_interval=0.01)

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket:
        assert websocket.receive_text() == "o"
        websocket.send_text(
            http_server.ujson.dumps(
                [
                    http_server.ujson.dumps(["VERSION", "alice", ""]),
                    http_server.ujson.dumps(
                        [
                            http_server.enums.CommandsToServer.SendGlobalChatMessage.value,
                            "sent before mapping",
                        ]
                    ),
                ]
            )
        )
        messages = decode_sockjs_messages(websocket.receive_text())
        heartbeat = websocket.receive_text()

    assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in messages
    assert [
        http_server.enums.CommandsToClient.AddGlobalChatMessage.value,
        1,
        "sent before mapping",
    ] not in messages
    assert heartbeat == "h"


def test_python_http_server_sockjs_websocket_closes_non_string_login_fields(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        raise TypeError("login fields must be strings")

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket,
    ):
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", 1, ""]))
        websocket.receive_text()


def test_python_http_server_sockjs_websocket_closes_when_server_disconnects(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    gateway = http_server.realtime.SockJSGateway()
    client, _main_root, _stats_root = make_client(tmp_path, realtime_gateway=gateway)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket,
    ):
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in (
            decode_sockjs_messages(websocket.receive_text())
        )
        gateway.write_from_game_server(b"disconnect 1\n")
        websocket.receive_text()


def test_python_http_server_sockjs_websocket_ignores_empty_frames(tmp_path, monkeypatch):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path)

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket:
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in (
            decode_sockjs_messages(websocket.receive_text())
        )
        websocket.send_text("")
        websocket.send_text(
            encode_sockjs_message(
                [
                    http_server.enums.CommandsToServer.SendGlobalChatMessage.value,
                    "after empty frame",
                ]
            )
        )
        messages = decode_sockjs_messages(websocket.receive_text())

    assert [
        http_server.enums.CommandsToClient.AddGlobalChatMessage.value,
        1,
        "after empty frame",
    ] in messages


def test_python_http_server_sockjs_websocket_closes_invalid_post_login_frames(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket,
    ):
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in (
            decode_sockjs_messages(websocket.receive_text())
        )
        websocket.send_text("not json")
        websocket.receive_text()


def test_python_http_server_sockjs_websocket_drops_frames_before_login_maps(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        time.sleep(0.05)
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path, sockjs_heartbeat_interval=0.01)

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket:
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        websocket.send_text(
            encode_sockjs_message(
                [
                    http_server.enums.CommandsToServer.SendGlobalChatMessage.value,
                    "sent before mapping",
                ]
            )
        )
        assert websocket.receive_text() == "h"
        assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in (
            decode_sockjs_messages(receive_next_sockjs_message_frame(websocket))
        )


def test_python_http_server_sockjs_websocket_stops_batch_after_disconnect(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    gateway = http_server.realtime.SockJSGateway()
    client, _main_root, _stats_root = make_client(tmp_path, realtime_gateway=gateway)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket,
    ):
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in (
            decode_sockjs_messages(websocket.receive_text())
        )
        websocket.send_text(
            http_server.ujson.dumps(
                [
                    "not json",
                    http_server.ujson.dumps(
                        [
                            http_server.enums.CommandsToServer.CreateGame.value,
                            http_server.enums.GameModes.Singles.value,
                            2,
                        ]
                    ),
                ]
            )
        )
        websocket.receive_text()

    assert gateway.game_server.game_id_to_game == {}


def test_python_http_server_sockjs_websocket_stops_queued_frames_after_disconnect(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    gateway = http_server.realtime.SockJSGateway()
    client, _main_root, _stats_root = make_client(tmp_path, realtime_gateway=gateway)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket,
    ):
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in (
            decode_sockjs_messages(websocket.receive_text())
        )
        websocket.send_text("not json")
        websocket.send_text(
            encode_sockjs_message(
                [
                    http_server.enums.CommandsToServer.CreateGame.value,
                    http_server.enums.GameModes.Singles.value,
                    2,
                ]
            )
        )
        websocket.receive_text()

    assert gateway.game_server.game_id_to_game == {}


def test_python_http_server_sockjs_websocket_forwards_authenticated_messages(
    tmp_path, monkeypatch
):
    def check_login(session_arg, **kwargs):
        return http_server.auth.LoginResult(None, "alice", "", False)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)
    client, _main_root, _stats_root = make_client(tmp_path)

    with client.websocket_connect("/sockjs/000/socket-alice/websocket") as websocket:
        assert websocket.receive_text() == "o"
        websocket.send_text(encode_sockjs_message(["VERSION", "alice", ""]))
        assert [http_server.enums.CommandsToClient.SetClientId.value, 1] in (
            decode_sockjs_messages(websocket.receive_text())
        )

        websocket.send_text(
            encode_sockjs_message(
                [
                    http_server.enums.CommandsToServer.SendGlobalChatMessage.value,
                    " hello from python gateway ",
                ]
            )
        )
        messages = decode_sockjs_messages(websocket.receive_text())

    assert [
        http_server.enums.CommandsToClient.AddGlobalChatMessage.value,
        1,
        "hello from python gateway",
    ] in messages


def test_python_http_server_set_password_persists_valid_password(tmp_path, monkeypatch):
    session = object()
    calls = []
    body = urllib.parse.urlencode(
        {
            "version": " VERSION ",
            "username": " alice ",
            "password": "a" * 64,
        }
    )

    def set_password(session_arg, **kwargs):
        calls.append((session_arg, kwargs))
        return None

    client, _main_root, _stats_root = make_client(
        tmp_path,
        session_scope=lambda: fake_session_scope(session),
        accepted_client_version="VERSION",
    )
    monkeypatch.setattr(http_server.auth, "set_password", set_password)

    response = client.post(
        "/server/set-password",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-length"] == "4"
    assert response.content == b"null"
    assert calls == [
        (
            session,
            {
                "version": " VERSION ",
                "username": " alice ",
                "password": "a" * 64,
                "server_version": "VERSION",
            },
        )
    ]


def test_check_login_in_session_rolls_back_generic_login_errors(monkeypatch):
    session = RollbackTrackingSession()

    def check_login(session_arg, **kwargs):
        assert session_arg is session
        return http_server.auth.LoginResult(http_server.enums.Errors.GenericError)

    monkeypatch.setattr(http_server.auth, "check_login", check_login)

    result = http_server.check_login_in_session(
        session_scope=lambda: fake_session_scope(session),
        version="VERSION",
        username="alice",
        password="",
        accepted_client_version="VERSION",
    )

    assert result.error is http_server.enums.Errors.GenericError
    assert session.rolled_back is True


def test_python_http_server_set_password_runs_database_work_in_threadpool(tmp_path, monkeypatch):
    threadpool_calls = []

    async def run_in_threadpool(func, **kwargs):
        threadpool_calls.append((func, kwargs))
        return enums.Errors.NotUsingLatestVersion

    client, _main_root, _stats_root = make_client(tmp_path)
    monkeypatch.setattr(http_server, "run_in_threadpool", run_in_threadpool)

    response = client.post(
        "/server/set-password",
        content=urllib.parse.urlencode({"version": "old"}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.content == b"0"
    assert len(threadpool_calls) == 1
    assert threadpool_calls[0][0] is http_server.set_password_in_session
    assert threadpool_calls[0][1]["accepted_client_version"] == "VERSION"


def test_python_http_server_set_password_returns_legacy_error_body(tmp_path, monkeypatch):
    def set_password(session_arg, **kwargs):
        return enums.Errors.NotUsingLatestVersion

    client, _main_root, _stats_root = make_client(tmp_path)
    monkeypatch.setattr(http_server.auth, "set_password", set_password)

    response = client.post(
        "/server/set-password",
        content=urllib.parse.urlencode({"version": "old"}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.content == b"0"


def test_python_http_server_rejects_invalid_set_password_content_length(tmp_path):
    client, _main_root, _stats_root = make_client(tmp_path)

    response = client.post(
        "/server/set-password",
        content=b"",
        headers={"Content-Length": str(http_server.MAX_REPORT_ERROR_BODY_BYTES + 1)},
    )

    assert response.status_code == 413


def test_create_app_returns_configured_fastapi_app(tmp_path):
    log_output = io.StringIO()
    main_root = tmp_path / "main"
    stats_root = tmp_path / "stats"

    app = http_server.create_app(
        main_static_root=main_root,
        stats_static_root=stats_root,
        log_output=log_output,
        session_scope=lambda: fake_session_scope(object()),
        accepted_client_version="TEST",
    )

    assert app.title == "Acquire Python HTTP"


def test_parse_args_accepts_http_server_options(tmp_path):
    args = http_server.parse_args(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "19001",
            "--main-static-root",
            str(tmp_path / "main"),
            "--stats-static-root",
            str(tmp_path / "stats"),
        ]
    )

    assert args.host == "127.0.0.1"
    assert args.port == 19001
    assert args.main_static_root == tmp_path / "main"
    assert args.stats_static_root == tmp_path / "stats"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--port", "0"],
        ["--port", "65536"],
        ["--port", "not-a-port"],
        ["--main-static-root", "private/relative/main"],
        ["--stats-static-root", "private/relative/stats"],
        ["--unknown"],
    ],
)
def test_parse_args_rejects_invalid_gateway_configuration_with_fixed_diagnostic(
    arguments,
    capsys,
):
    with pytest.raises(SystemExit) as exit_info:
        http_server.parse_args(arguments)

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert captured.out == ""
    assert captured.err == "error: invalid arguments\n"


@pytest.mark.parametrize(
    "private_root",
    [
        "/private/missing/root",
        r"/private\/missing\/root",
        "/private%2Fmissing%2Froot",
        "/private%252Fmissing%252Froot",
    ],
)
def test_main_rejects_missing_static_roots_without_reflecting_them(
    private_root,
    monkeypatch,
    tmp_path,
    capsys,
):
    calls = []
    monkeypatch.setattr(
        http_server,
        "run_http_server",
        lambda **kwargs: calls.append(kwargs),
    )
    stats_root = tmp_path / "stats"
    stats_root.mkdir()

    result = http_server.main(
        [
            "--main-static-root",
            private_root,
            "--stats-static-root",
            str(stats_root),
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert calls == []
    assert captured.out == ""
    assert captured.err == "error: HTTP server configuration failed\n"
    assert private_root not in captured.err


def test_main_rejects_file_static_root_before_starting_server(
    monkeypatch,
    tmp_path,
    capsys,
):
    main_root = tmp_path / "main"
    stats_root = tmp_path / "stats"
    main_root.mkdir()
    stats_root.write_text("not a directory")
    calls = []
    monkeypatch.setattr(
        http_server,
        "run_http_server",
        lambda **kwargs: calls.append(kwargs),
    )

    result = http_server.main(
        [
            "--main-static-root",
            str(main_root),
            "--stats-static-root",
            str(stats_root),
        ]
    )

    assert result == 1
    assert calls == []
    assert capsys.readouterr().err == "error: HTTP server configuration failed\n"


def test_run_http_server_builds_uvicorn_app(monkeypatch, tmp_path):
    calls = []

    class Listener:
        def setsockopt(self, level, option, value):
            calls.append(("setsockopt", level, option, value))

        def bind(self, address):
            calls.append(("bind", address))

        def set_inheritable(self, inheritable):
            calls.append(("set_inheritable", inheritable))

        def close(self):
            calls.append(("close",))

    listener = Listener()

    def create_socket(*, family):
        calls.append(("socket", family))
        return listener

    class Server:
        def __init__(self, config):
            calls.append(("server", config.app.title, config.host, config.port))

        def run(self, *, sockets):
            calls.append(("run", sockets))

    monkeypatch.setattr(http_server.socket, "socket", create_socket)
    monkeypatch.setattr(
        http_server.uvicorn,
        "Config",
        lambda app, host, port: SimpleNamespace(app=app, host=host, port=port),
    )
    monkeypatch.setattr(http_server.uvicorn, "Server", Server)

    http_server.run_http_server(
        host="127.0.0.1",
        port=19001,
        main_static_root=tmp_path / "main",
        stats_static_root=tmp_path / "stats",
    )

    assert calls == [
        ("socket", http_server.socket.AF_INET),
        (
            "setsockopt",
            http_server.socket.SOL_SOCKET,
            http_server.socket.SO_REUSEADDR,
            1,
        ),
        ("bind", ("127.0.0.1", 19001)),
        ("set_inheritable", True),
        ("server", "Acquire Python HTTP", "127.0.0.1", 19001),
        ("run", [listener]),
        ("close",),
    ]


def test_run_http_server_closes_listener_after_server_failure(monkeypatch, tmp_path):
    class Listener:
        closed = False

        def setsockopt(self, level, option, value):
            pass

        def bind(self, address):
            pass

        def set_inheritable(self, inheritable):
            pass

        def close(self):
            self.closed = True

    listener = Listener()

    class Server:
        def __init__(self, config):
            pass

        def run(self, *, sockets):
            raise RuntimeError("server failed")

    monkeypatch.setattr(http_server.socket, "socket", lambda *, family: listener)
    monkeypatch.setattr(http_server.uvicorn, "Server", Server)

    with pytest.raises(RuntimeError, match="server failed"):
        http_server.run_http_server(
            host="::1",
            port=19001,
            main_static_root=tmp_path / "main",
            stats_static_root=tmp_path / "stats",
        )

    assert listener.closed


def test_run_http_server_sanitizes_listener_bind_failure(monkeypatch, tmp_path):
    class Listener:
        closed = False

        def setsockopt(self, level, option, value):
            pass

        def bind(self, address):
            raise OSError(f"private bind failure for {address}")

        def close(self):
            self.closed = True

    listener = Listener()
    monkeypatch.setattr(http_server.socket, "socket", lambda *, family: listener)

    with pytest.raises(http_server.HttpServerBindError) as exit_info:
        http_server.run_http_server(
            host="private-host",
            port=19001,
            main_static_root=tmp_path / "main",
            stats_static_root=tmp_path / "stats",
        )

    assert str(exit_info.value) == ""
    assert listener.closed


def test_run_http_server_sanitizes_listener_creation_failure(monkeypatch, tmp_path):
    def create_socket(*, family):
        raise OSError("private socket setup failure")

    monkeypatch.setattr(http_server.socket, "socket", create_socket)

    with pytest.raises(http_server.HttpServerBindError) as exit_info:
        http_server.run_http_server(
            host="private-host",
            port=19001,
            main_static_root=tmp_path / "main",
            stats_static_root=tmp_path / "stats",
        )

    assert str(exit_info.value) == ""


@pytest.mark.parametrize(
    "private_host",
    [
        "private-host.internal",
        r"private-host\.internal",
        "private-host%2Einternal",
        "private-host%252Einternal",
    ],
)
def test_main_redacts_listener_bind_failure(
    private_host,
    monkeypatch,
    tmp_path,
    capsys,
):
    main_root = tmp_path / "main"
    stats_root = tmp_path / "stats"
    main_root.mkdir()
    stats_root.mkdir()
    monkeypatch.setattr(
        http_server,
        "run_http_server",
        lambda **kwargs: (_ for _ in ()).throw(
            http_server.HttpServerBindError(private_host)
        ),
    )

    result = http_server.main(
        [
            "--host",
            private_host,
            "--main-static-root",
            str(main_root),
            "--stats-static-root",
            str(stats_root),
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: HTTP server configuration failed\n"
    assert private_host not in captured.err


def test_main_runs_http_server_with_parsed_args(monkeypatch, tmp_path):
    calls = []
    main_root = tmp_path / "main"
    stats_root = tmp_path / "stats"
    main_root.mkdir()
    stats_root.mkdir()

    def run_http_server(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(http_server, "run_http_server", run_http_server)

    result = http_server.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "19002",
            "--main-static-root",
            str(main_root),
            "--stats-static-root",
            str(stats_root),
        ]
    )

    assert result == 0
    assert calls == [
        {
            "host": "127.0.0.1",
            "port": 19002,
            "main_static_root": main_root,
            "stats_static_root": stats_root,
        }
    ]
