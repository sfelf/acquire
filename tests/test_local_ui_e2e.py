import time
import urllib.error
import urllib.parse
import urllib.request

import pytest


pytestmark = pytest.mark.e2e


def _read_url(url_or_request, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(url_or_request, timeout=5) as response:
                return response.status, response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def test_legacy_gateway_serves_main_ui(e2e_base_url):
    status, body = _read_url(e2e_base_url.rstrip("/") + "/")

    assert status == 200
    assert "Acquire" in body
    assert 'id="page-login"' in body


def test_legacy_gateway_serves_stats_ui(e2e_base_url):
    status, body = _read_url(e2e_base_url.rstrip("/") + "/stats/")

    assert status == 200
    assert "Acquire stats" in body
    assert 'id="page-stats"' in body


def test_legacy_gateway_accepts_report_error_posts(e2e_base_url):
    data = urllib.parse.urlencode(
        {
            "message": "e2e smoke",
            "trace": "client trace",
        }
    ).encode()
    request = urllib.request.Request(
        e2e_base_url.rstrip("/") + "/server/report-error",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    status, body = _read_url(request)

    assert status == 200
    assert body == ""
