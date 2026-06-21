import email.message
import io
import urllib.parse
from http import HTTPStatus

import http_server
import pytest

pytestmark = pytest.mark.unit


def make_handler(tmp_path, path="/", method="GET", body=b"", log_output=None):
    main_root = tmp_path / "main"
    stats_root = tmp_path / "stats"
    main_root.mkdir(exist_ok=True)
    stats_root.mkdir(exist_ok=True)

    handler = http_server.AcquireHTTPRequestHandler.__new__(
        http_server.AcquireHTTPRequestHandler
    )
    handler.main_static_root = main_root
    handler.stats_static_root = stats_root
    handler.log_output = log_output or io.StringIO()
    handler.path = path
    handler.command = method
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.responses = []
    handler.headers_sent = []
    headers = email.message.Message()
    headers["Content-Length"] = str(len(body))
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    handler.headers = headers

    def send_response(status):
        handler.responses.append(status)

    def send_header(name, value):
        handler.headers_sent.append((name, value))

    def end_headers():
        handler.headers_ended = True

    def send_error(status):
        handler.responses.append(status)
        handler.headers_ended = True

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    handler.send_error = send_error
    return handler


def test_python_http_server_serves_main_static_assets(tmp_path):
    handler = make_handler(tmp_path)
    (handler.main_static_root / "css").mkdir()
    (handler.main_static_root / "index.html").write_text("<h1>Acquire</h1>", encoding="utf-8")
    (handler.main_static_root / "css" / "main.css").write_text(
        "body { color: black; }",
        encoding="utf-8",
    )

    handler.do_GET()
    index_body = handler.wfile.getvalue()

    css_handler = make_handler(tmp_path, "/css/main.css")
    css_handler.main_static_root = handler.main_static_root
    css_handler.stats_static_root = handler.stats_static_root
    css_handler.do_GET()

    assert handler.responses == [HTTPStatus.OK]
    assert ("Content-Type", "text/html") in handler.headers_sent
    assert index_body == b"<h1>Acquire</h1>"
    assert css_handler.responses == [HTTPStatus.OK]
    assert ("Content-Type", "text/css") in css_handler.headers_sent
    assert css_handler.wfile.getvalue() == b"body { color: black; }"


def test_python_http_server_serves_stats_static_assets(tmp_path):
    handler = make_handler(tmp_path, "/stats/")
    (handler.stats_static_root / "js").mkdir()
    (handler.stats_static_root / "index.html").write_text(
        "<h1>Acquire stats</h1>",
        encoding="utf-8",
    )
    (handler.stats_static_root / "js" / "stats.js").write_text(
        "window.stats = true;",
        encoding="utf-8",
    )

    handler.do_GET()
    index_body = handler.wfile.getvalue()

    js_handler = make_handler(tmp_path, "/stats/js/stats.js")
    js_handler.main_static_root = handler.main_static_root
    js_handler.stats_static_root = handler.stats_static_root
    js_handler.do_GET()

    assert handler.responses == [HTTPStatus.OK]
    assert ("Content-Type", "text/html") in handler.headers_sent
    assert index_body == b"<h1>Acquire stats</h1>"
    assert js_handler.responses == [HTTPStatus.OK]
    assert ("Content-Type", "text/javascript") in js_handler.headers_sent
    assert js_handler.wfile.getvalue() == b"window.stats = true;"


def test_python_http_server_redirects_stats_index_without_trailing_slash(tmp_path):
    handler = make_handler(tmp_path, "/stats")
    (handler.stats_static_root / "index.html").write_text(
        "<h1>Acquire stats</h1>",
        encoding="utf-8",
    )

    handler.do_GET()

    assert handler.responses == [HTTPStatus.MOVED_PERMANENTLY]
    assert ("Location", "/stats/") in handler.headers_sent
    assert handler.wfile.getvalue() == b""


def test_python_http_server_redirects_stats_query_to_slash_path(tmp_path):
    handler = make_handler(tmp_path, "/stats?ratings=singles")

    handler.do_GET()

    assert handler.responses == [HTTPStatus.MOVED_PERMANENTLY]
    assert ("Location", "/stats/?ratings=singles") in handler.headers_sent
    assert handler.wfile.getvalue() == b""


def test_python_http_server_redirects_stats_head_requests(tmp_path):
    handler = make_handler(tmp_path, "/stats", method="HEAD")

    handler.do_HEAD()

    assert handler.responses == [HTTPStatus.MOVED_PERMANENTLY]
    assert ("Location", "/stats/") in handler.headers_sent
    assert handler.wfile.getvalue() == b""


def test_python_http_server_rejects_path_traversal(tmp_path):
    handler = make_handler(tmp_path, "/../secret.txt")
    (tmp_path / "secret.txt").write_text("hidden", encoding="utf-8")

    handler.do_GET()

    assert handler.responses == [HTTPStatus.NOT_FOUND]
    assert handler.wfile.getvalue() == b""


def test_safe_join_normalizes_empty_paths_to_index(tmp_path):
    root = tmp_path / "main"
    root.mkdir()

    assert http_server.AcquireHTTPRequestHandler._safe_join(root, ".") == (
        root / "index.html"
    ).resolve()


def test_python_http_server_head_sends_headers_without_body(tmp_path):
    handler = make_handler(tmp_path, method="HEAD")
    (handler.main_static_root / "index.html").write_text("<h1>Acquire</h1>", encoding="utf-8")

    handler.do_HEAD()

    assert handler.responses == [HTTPStatus.OK]
    assert ("Content-Length", "16") in handler.headers_sent
    assert handler.wfile.getvalue() == b""


def test_python_http_server_accepts_report_error_posts(tmp_path):
    log_output = io.StringIO()
    body = urllib.parse.urlencode(
        {
            "message": "first\nsecond",
            "trace": "trace\nline",
        }
    ).encode()
    handler = make_handler(
        tmp_path,
        "/server/report-error",
        method="POST",
        body=body,
        log_output=log_output,
    )

    handler.do_POST()

    assert handler.responses == [HTTPStatus.OK]
    assert handler.wfile.getvalue() == b""
    assert "/server/report-error: first\n\tsecond" in log_output.getvalue()
    assert "\ttrace\n\tline" in log_output.getvalue()


def test_python_http_server_report_error_logs_null_missing_fields(tmp_path):
    log_output = io.StringIO()
    handler = make_handler(
        tmp_path,
        "/server/report-error",
        method="POST",
        body=b"",
        log_output=log_output,
    )

    handler.do_POST()

    assert handler.responses == [HTTPStatus.OK]
    assert handler.wfile.getvalue() == b""
    assert "/server/report-error: <null>" in log_output.getvalue()
    assert "\t<null>" in log_output.getvalue()


def test_python_http_server_rejects_oversized_report_error_before_reading(tmp_path):
    log_output = io.StringIO()
    handler = make_handler(
        tmp_path,
        "/server/report-error",
        method="POST",
        body=b"",
        log_output=log_output,
    )
    handler.headers.replace_header(
        "Content-Length",
        str(http_server.MAX_REPORT_ERROR_BODY_BYTES + 1),
    )

    handler.do_POST()

    assert handler.responses == [HTTPStatus.REQUEST_ENTITY_TOO_LARGE]
    assert handler.wfile.getvalue() == b""
    assert log_output.getvalue() == ""


@pytest.mark.parametrize("content_length", ["not-a-number", "-1"])
def test_python_http_server_rejects_invalid_report_error_content_length(
    tmp_path,
    content_length,
):
    log_output = io.StringIO()
    handler = make_handler(
        tmp_path,
        "/server/report-error",
        method="POST",
        body=b"",
        log_output=log_output,
    )
    handler.headers.replace_header("Content-Length", content_length)

    handler.do_POST()

    assert handler.responses == [HTTPStatus.BAD_REQUEST]
    assert handler.wfile.getvalue() == b""
    assert log_output.getvalue() == ""


def test_python_http_server_rejects_unknown_post_routes(tmp_path):
    handler = make_handler(tmp_path, "/server/set-password", method="POST")

    handler.do_POST()

    assert handler.responses == [HTTPStatus.NOT_FOUND]


def test_make_handler_returns_configured_handler_class(tmp_path):
    log_output = io.StringIO()
    main_root = tmp_path / "main"
    stats_root = tmp_path / "stats"

    handler_class = http_server.make_handler(
        main_static_root=main_root,
        stats_static_root=stats_root,
        log_output=log_output,
    )

    assert issubclass(handler_class, http_server.AcquireHTTPRequestHandler)
    assert handler_class.main_static_root == main_root
    assert handler_class.stats_static_root == stats_root
    assert handler_class.log_output == log_output


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


def test_run_http_server_builds_threading_server(monkeypatch, tmp_path):
    calls = []

    class FakeHTTPServer:
        def __init__(self, address, handler):
            self.address = address
            self.handler = handler
            calls.append(("init", address, handler.main_static_root, handler.stats_static_root))

        def __enter__(self):
            calls.append(("enter",))
            return self

        def __exit__(self, exc_type, exc, traceback):
            calls.append(("exit", exc_type, exc, traceback))

        def serve_forever(self):
            calls.append(("serve_forever", self.address))

    monkeypatch.setattr(http_server, "ThreadingHTTPServer", FakeHTTPServer)

    http_server.run_http_server(
        host="127.0.0.1",
        port=19001,
        main_static_root=tmp_path / "main",
        stats_static_root=tmp_path / "stats",
    )

    assert calls == [
        (
            "init",
            ("127.0.0.1", 19001),
            tmp_path / "main",
            tmp_path / "stats",
        ),
        ("enter",),
        ("serve_forever", ("127.0.0.1", 19001)),
        ("exit", None, None, None),
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
