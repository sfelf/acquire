"""Serve Python-owned HTTP routes with FastAPI during backend consolidation.

This module is the Phase 5 landing place for non-websocket routes that are
moving out of the legacy Node gateway. FastAPI owns the route table and ASGI
runtime while the route implementations preserve legacy response bodies and
normalization rules for compatibility with the existing client.
"""

from __future__ import annotations

import argparse
import mimetypes
import posixpath
import sys
import urllib.parse
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Literal, TextIO

import auth
import enums
import orm
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette import status
from starlette.concurrency import run_in_threadpool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAIN_STATIC_ROOT = PROJECT_ROOT / "client" / "main"
DEFAULT_STATS_STATIC_ROOT = PROJECT_ROOT / "client" / "stats"
MAX_REPORT_ERROR_BODY_BYTES = 100 * 1024
SERVER_VERSION = "VERSION"
SessionScope = Callable[[], AbstractContextManager[auth.AuthSession]]


class ReportErrorForm(BaseModel):
    """Represent a legacy `/server/report-error` form payload."""

    message: str | None = None
    trace: str | None = None

    def legacy_value(self, key: Literal["message", "trace"]) -> str:
        """Return a Node-compatible report-error field value.

        Args:
            key: Report-error field name to format.

        Returns:
            Parsed value with embedded newlines indented, or `<null>` when the
            field was not submitted.
        """
        value = self.message if key == "message" else self.trace
        if value is None:
            return "<null>"
        return value.replace("\n", "\n\t")


class SetPasswordForm(BaseModel):
    """Represent a legacy `/server/set-password` form payload.

    The fields remain optional so missing values reach the auth layer as
    `None`, preserving the legacy endpoint's error-code contract instead of
    turning malformed form submissions into framework-level validation errors.
    """

    version: str | None = None
    username: str | None = None
    password: str | None = None


def parse_form_body(body: bytes) -> dict[str, list[str]]:
    """Parse URL-encoded form bytes with legacy blank-value handling.

    Args:
        body: Raw request body bytes.

    Returns:
        Parsed form data keyed by submitted field name.
    """
    return urllib.parse.parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)


def first_form_value(form_data: dict[str, list[str]], key: str) -> str | None:
    """Return the first submitted form value.

    Args:
        form_data: Parsed form data keyed by field name.
        key: Field name to read.

    Returns:
        First submitted value, or `None` when the field was not submitted.
    """
    values = form_data.get(key)
    return values[0] if values else None


def safe_join(root: Path, relative_path: str) -> Path | None:
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


def validate_content_length(request: Request) -> int:
    """Return a safe request body length or raise the matching HTTP error.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Parsed request body length.

    Raises:
        HTTPException: If the content length is invalid or exceeds the legacy
            maximum accepted body size.
    """
    content_length_header = request.headers.get("content-length")
    if content_length_header is None:
        raise HTTPException(status_code=status.HTTP_411_LENGTH_REQUIRED)

    try:
        content_length = int(content_length_header)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from exc

    if content_length < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    if content_length > MAX_REPORT_ERROR_BODY_BYTES:
        raise HTTPException(status_code=413)

    return content_length


def set_password_in_session(
    *,
    session_scope: SessionScope,
    form: SetPasswordForm,
    accepted_client_version: str,
) -> enums.Errors | None:
    """Persist a password setup request inside a database session.

    This function performs synchronous SQLAlchemy work and is called from the
    FastAPI route through Starlette's threadpool. Keeping it separate preserves
    the previous threaded behavior: a slow MySQL lookup or flush should not
    block the ASGI event loop from serving unrelated requests.

    Args:
        session_scope: Context manager factory for database sessions.
        form: Parsed set-password form payload.
        accepted_client_version: Accepted client version token.

    Returns:
        Legacy error value, or `None` when password setup succeeds.
    """
    with session_scope() as session:
        return auth.set_password(
            session,
            version=form.version,
            username=form.username,
            password=form.password,
            server_version=accepted_client_version,
        )


def resolve_static_path(
    path: str,
    *,
    main_static_root: Path,
    stats_static_root: Path,
) -> Path | None:
    """Resolve a request path into one of the generated static roots.

    Args:
        path: Decoded URL path.
        main_static_root: Root directory for generated `client/main` assets.
        stats_static_root: Root directory for generated `client/stats` assets.

    Returns:
        Static file path for a valid in-tree request, otherwise `None`.
    """
    if path == "/stats/" or path.startswith("/stats/"):
        relative_path = path.removeprefix("/stats/") or "index.html"
        return safe_join(stats_static_root, relative_path)

    relative_path = path.removeprefix("/") or "index.html"
    return safe_join(main_static_root, relative_path)


def create_app(
    *,
    main_static_root: Path = DEFAULT_MAIN_STATIC_ROOT,
    stats_static_root: Path = DEFAULT_STATS_STATIC_ROOT,
    log_output: TextIO = sys.stdout,
    session_scope: SessionScope = orm.session_scope,
    accepted_client_version: str = SERVER_VERSION,
) -> FastAPI:
    """Create the FastAPI app for Python-owned HTTP routes.

    The app serves generated static files, logs report-error submissions, and
    persists password setup requests through the Python auth module. It does not
    serve SockJS traffic yet; the legacy Node gateway remains the realtime path
    until a later Phase 5 PR replaces it.

    Args:
        main_static_root: Root directory for generated `client/main` assets.
        stats_static_root: Root directory for generated `client/stats` assets.
        log_output: Stream that receives report-error log lines.
        session_scope: Context manager factory for database sessions.
        accepted_client_version: Accepted client version token.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Acquire Python HTTP",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.api_route("/server/report-error", methods=["POST"])
    async def report_error(request: Request) -> Response:
        """Log a client error report and return the legacy empty response.

        Args:
            request: Incoming form-encoded report-error request.

        Returns:
            Empty 200 response matching the legacy Node endpoint.
        """
        validate_content_length(request)
        form_data = parse_form_body(await request.body())
        form = ReportErrorForm(
            message=first_form_value(form_data, "message"),
            trace=first_form_value(form_data, "trace"),
        )

        print(f"/server/report-error: {form.legacy_value('message')}", file=log_output)
        print(f"\t{form.legacy_value('trace')}", file=log_output)
        print(f"  {dict(request.headers)}", file=log_output)
        return Response(status_code=status.HTTP_200_OK)

    @app.api_route("/server/set-password", methods=["POST"])
    async def set_password(request: Request) -> Response:
        """Set a user password through the Python auth implementation.

        The endpoint preserves the legacy JSON-ish response contract by
        returning the string `null` on success or a stringified numeric
        `Errors` value on failure. Password persistence uses synchronous
        SQLAlchemy, so the database section runs in a threadpool to avoid
        blocking the ASGI event loop.

        Args:
            request: Incoming form-encoded set-password request.

        Returns:
            JSON response body containing `null` or the legacy error id.
        """
        validate_content_length(request)
        form_data = parse_form_body(await request.body())
        form = SetPasswordForm(
            version=first_form_value(form_data, "version"),
            username=first_form_value(form_data, "username"),
            password=first_form_value(form_data, "password"),
        )

        error = await run_in_threadpool(
            set_password_in_session,
            session_scope=session_scope,
            form=form,
            accepted_client_version=accepted_client_version,
        )

        return Response(
            content=auth.error_response_text(error),
            media_type="application/json",
            status_code=status.HTTP_200_OK,
        )

    @app.api_route("/stats", methods=["GET", "HEAD"])
    async def redirect_stats_root(request: Request) -> RedirectResponse:
        """Redirect `/stats` requests to `/stats/`.

        The stats client uses relative asset URLs, so slashless requests must
        preserve the query string while adding the trailing slash. Without this
        redirect, browsers resolve stats CSS and JavaScript paths against the
        site root instead of the `/stats/` directory.

        Args:
            request: Incoming request whose query string should be preserved.

        Returns:
            Permanent redirect response pointing at `/stats/`.
        """
        location = urllib.parse.urlunsplit(("", "", "/stats/", request.url.query, ""))
        return RedirectResponse(location, status_code=status.HTTP_301_MOVED_PERMANENTLY)

    @app.api_route("/{request_path:path}", methods=["POST"])
    async def reject_unknown_post(request_path: str) -> None:
        """Return the legacy not-found response for unknown POST routes.

        Args:
            request_path: Unmatched request path.

        Raises:
            HTTPException: Always raised with a 404 status.
        """
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    @app.api_route("/{request_path:path}", methods=["GET", "HEAD"])
    async def serve_static(request_path: str, request: Request) -> FileResponse:
        """Serve a file from the generated main or stats asset trees.

        The route chooses the stats static root for `/stats/` requests and the
        main static root for every other GET/HEAD path. Resolved paths must stay
        inside the selected root; traversal attempts and missing files return
        404 instead of falling through to another handler.

        Args:
            request_path: FastAPI catch-all path component.
            request: Incoming request used to read the decoded URL path.

        Returns:
            File response for the generated static asset.

        Raises:
            HTTPException: If the resolved asset is missing or outside the
                selected static root.
        """
        decoded_path = urllib.parse.unquote(request.url.path)
        resolved = resolve_static_path(
            decoded_path,
            main_static_root=main_static_root,
            stats_static_root=stats_static_root,
        )
        if resolved is None or not resolved.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        content_type = mimetypes.guess_type(resolved)[0] or "application/octet-stream"
        return FileResponse(resolved, media_type=content_type)

    return app


def run_http_server(
    *,
    host: str,
    port: int,
    main_static_root: Path = DEFAULT_MAIN_STATIC_ROOT,
    stats_static_root: Path = DEFAULT_STATS_STATIC_ROOT,
    log_output: TextIO = sys.stdout,
) -> None:
    """Run the FastAPI HTTP server until interrupted.

    Args:
        host: Interface to bind.
        port: TCP port to bind.
        main_static_root: Root directory for generated `client/main` assets.
        stats_static_root: Root directory for generated `client/stats` assets.
        log_output: Stream that receives report-error log lines.
    """
    app = create_app(
        main_static_root=main_static_root,
        stats_static_root=stats_static_root,
        log_output=log_output,
    )
    uvicorn.run(app, host=host, port=port)


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
    main()
