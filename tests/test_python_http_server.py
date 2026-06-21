import io
import urllib.parse
from contextlib import contextmanager
from types import SimpleNamespace

import enums
import http_server
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def make_client(
    tmp_path,
    *,
    log_output=None,
    session_scope=None,
    accepted_client_version="VERSION",
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
    )
    return TestClient(app), main_root, stats_root


@contextmanager
def fake_session_scope(session):
    yield session


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


def test_run_http_server_builds_uvicorn_app(monkeypatch, tmp_path):
    calls = []

    def run(app, **kwargs):
        calls.append((app.title, kwargs))

    monkeypatch.setattr(http_server.uvicorn, "run", run)

    http_server.run_http_server(
        host="127.0.0.1",
        port=19001,
        main_static_root=tmp_path / "main",
        stats_static_root=tmp_path / "stats",
    )

    assert calls == [
        (
            "Acquire Python HTTP",
            {
                "host": "127.0.0.1",
                "port": 19001,
            },
        )
    ]


def test_main_runs_http_server_with_parsed_args(monkeypatch, tmp_path):
    calls = []

    def run_http_server(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(http_server, "run_http_server", run_http_server)

    http_server.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "19002",
            "--main-static-root",
            str(tmp_path / "main"),
            "--stats-static-root",
            str(tmp_path / "stats"),
        ]
    )

    assert calls == [
        {
            "host": "127.0.0.1",
            "port": 19002,
            "main_static_root": tmp_path / "main",
            "stats_static_root": tmp_path / "stats",
        }
    ]
