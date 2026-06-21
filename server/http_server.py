"""Serve Python-owned HTTP routes during backend consolidation.

This module is the Phase 5 landing place for non-websocket routes that are
currently served by the legacy Node gateway. It intentionally does not own
SockJS traffic or user/password persistence yet; those boundaries move in later
Phase 5 PRs after their behavior is characterized separately.
"""

from __future__ import annotations

import argparse
import mimetypes
import posixpath
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import TextIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAIN_STATIC_ROOT = PROJECT_ROOT / "client" / "main"
DEFAULT_STATS_STATIC_ROOT = PROJECT_ROOT / "client" / "stats"
MAX_REPORT_ERROR_BODY_BYTES = 100 * 1024


class AcquireHTTPRequestHandler(BaseHTTPRequestHandler):
    """Serve static client assets and legacy-compatible report-error posts.

    The handler mirrors only the non-websocket routes that can move without
    changing authentication or realtime behavior. `server/server.js` still owns
    SockJS and password persistence until later Phase 5 work moves those
    boundaries with MySQL-backed tests.
    """

    server_version = "AcquirePythonHTTP/0"
    main_static_root = DEFAULT_MAIN_STATIC_ROOT
    stats_static_root = DEFAULT_STATS_STATIC_ROOT
    log_output: TextIO = sys.stdout

    def do_GET(self) -> None:
        """Serve generated client assets."""
        if self._redirect_stats_root():
            return
        self._serve_static(send_body=True)

    def do_HEAD(self) -> None:
        """Serve generated client asset headers."""
        if self._redirect_stats_root():
            return
        self._serve_static(send_body=False)

    def do_POST(self) -> None:
        """Handle Python-owned POST routes."""
        if self.path.split("?", 1)[0] == "/server/report-error":
            self._handle_report_error()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format_: str, *args: object) -> None:
        """Suppress default access logging.

        The legacy Node gateway logs explicit report-error payloads but does not
        emit Python's default per-request access log format. Keeping this quiet
        also makes tests deterministic.

        Args:
            format_: Default `BaseHTTPRequestHandler` log format.
            *args: Values for the default log format.
        """

    def _serve_static(self, *, send_body: bool) -> None:
        """Serve a file from the generated main or stats asset trees.

        Args:
            send_body: Whether to write the file body after response headers.
        """
        resolved = self._resolve_static_path()
        if resolved is None or not resolved.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content = resolved.read_bytes()
        content_type = mimetypes.guess_type(resolved)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if send_body:
            self.wfile.write(content)

    def _redirect_stats_root(self) -> bool:
        """Redirect `/stats` requests to `/stats/`.

        The stats HTML uses relative asset URLs, so slashless requests must
        redirect before the page is served. Otherwise browsers resolve
        `css/stats.css` and `js/stats.js` against the site root instead of the
        `/stats/` directory.

        Returns:
            Whether a redirect response was sent.
        """
        split_url = urllib.parse.urlsplit(self.path)
        if split_url.path != "/stats":
            return False

        location = urllib.parse.urlunsplit(("", "", "/stats/", split_url.query, ""))
        self.send_response(HTTPStatus.MOVED_PERMANENTLY)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def _resolve_static_path(self) -> Path | None:
        """Resolve the request path into one of the generated static roots.

        Returns:
            Static file path for a valid in-tree request, otherwise `None`.
        """
        raw_path = urllib.parse.urlsplit(self.path).path
        decoded_path = urllib.parse.unquote(raw_path)

        if decoded_path == "/stats/" or decoded_path.startswith("/stats/"):
            relative_path = decoded_path.removeprefix("/stats/") or "index.html"
            return self._safe_join(self.stats_static_root, relative_path)

        relative_path = decoded_path.removeprefix("/") or "index.html"
        return self._safe_join(self.main_static_root, relative_path)

    @staticmethod
    def _safe_join(root: Path, relative_path: str) -> Path | None:
        """Return an in-tree path for a URL path fragment.

        Args:
            root: Static root directory.
            relative_path: URL path fragment relative to the static root.

        Returns:
            Resolved file path when the URL stays under `root`, otherwise `None`.
        """
        normalized = posixpath.normpath(relative_path)
        if normalized in {"", "."}:
            normalized = "index.html"
        candidate = (root / normalized).resolve()
        resolved_root = root.resolve()
        if candidate == resolved_root or resolved_root not in candidate.parents:
            return None
        return candidate

    def _handle_report_error(self) -> None:
        """Log a client error report and return the legacy empty response."""
        content_length_header = self.headers.get("Content-Length", "0") or "0"
        try:
            content_length = int(content_length_header)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        if content_length < 0:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        if content_length > MAX_REPORT_ERROR_BODY_BYTES:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return

        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        form_data = urllib.parse.parse_qs(body, keep_blank_values=True)
        message = self._report_error_value(form_data, "message")
        trace = self._report_error_value(form_data, "trace")

        print(f"/server/report-error: {message}", file=self.log_output)
        print(f"\t{trace}", file=self.log_output)
        print(f"  {dict(self.headers)}", file=self.log_output)

        self.send_response(HTTPStatus.OK)
        self.end_headers()

    @staticmethod
    def _report_error_value(form_data: dict[str, list[str]], key: str) -> str:
        """Return a Node-compatible report-error form value.

        Args:
            form_data: Parsed form data keyed by field name.
            key: Field name to read.

        Returns:
            Parsed value with embedded newlines indented, or `<null>` when the
            field was not submitted.
        """
        if key not in form_data:
            return "<null>"
        return form_data[key][0].replace("\n", "\n\t")


def make_handler(
    *,
    main_static_root: Path = DEFAULT_MAIN_STATIC_ROOT,
    stats_static_root: Path = DEFAULT_STATS_STATIC_ROOT,
    log_output: TextIO = sys.stdout,
) -> type[AcquireHTTPRequestHandler]:
    """Build a configured HTTP handler class.

    Args:
        main_static_root: Root directory for generated `client/main` assets.
        stats_static_root: Root directory for generated `client/stats` assets.
        log_output: Stream that receives report-error log lines.

    Returns:
        Handler class ready to pass to `ThreadingHTTPServer`.
    """

    return type(
        "ConfiguredAcquireHTTPRequestHandler",
        (AcquireHTTPRequestHandler,),
        {
            "__doc__": "HTTP handler with configured static roots and log stream.",
            "main_static_root": main_static_root,
            "stats_static_root": stats_static_root,
            "log_output": log_output,
        },
    )


def run_http_server(
    *,
    host: str,
    port: int,
    main_static_root: Path = DEFAULT_MAIN_STATIC_ROOT,
    stats_static_root: Path = DEFAULT_STATS_STATIC_ROOT,
    log_output: TextIO = sys.stdout,
) -> None:
    """Run the Python HTTP server until interrupted.

    Args:
        host: Interface to bind.
        port: TCP port to bind.
        main_static_root: Root directory for generated `client/main` assets.
        stats_static_root: Root directory for generated `client/stats` assets.
        log_output: Stream that receives report-error log lines.
    """
    handler = make_handler(
        main_static_root=main_static_root,
        stats_static_root=stats_static_root,
        log_output=log_output,
    )
    with ThreadingHTTPServer((host, port), handler) as httpd:
        httpd.serve_forever()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list. Uses `sys.argv` when omitted.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(description="Serve Acquire HTTP routes from Python.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--main-static-root", type=Path, default=DEFAULT_MAIN_STATIC_ROOT)
    parser.add_argument("--stats-static-root", type=Path, default=DEFAULT_STATS_STATIC_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the command-line HTTP server.

    Args:
        argv: Optional argument list. Uses `sys.argv` when omitted.
    """
    args = parse_args(argv)
    run_http_server(
        host=args.host,
        port=args.port,
        main_static_root=args.main_static_root,
        stats_static_root=args.stats_static_root,
    )


if __name__ == "__main__":
    TCPServer.allow_reuse_address = True
    main()
