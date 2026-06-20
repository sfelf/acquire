import time
import urllib.error
import urllib.request

import pytest


pytestmark = pytest.mark.e2e


def test_legacy_gateway_serves_local_ui(e2e_base_url):
    deadline = time.monotonic() + 60
    while True:
        try:
            with urllib.request.urlopen(e2e_base_url.rstrip("/") + "/", timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace")
                status = response.status
            break
        except urllib.error.URLError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)

    assert status == 200
    assert "Acquire" in body
