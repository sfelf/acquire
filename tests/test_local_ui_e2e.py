import os
import urllib.request

import pytest


pytestmark = pytest.mark.e2e


def test_legacy_gateway_serves_local_ui():
    base_url = os.environ.get("ACQUIRE_E2E_URL")
    if not base_url:
        pytest.skip("ACQUIRE_E2E_URL is required for e2e smoke tests")

    with urllib.request.urlopen(base_url.rstrip("/") + "/", timeout=5) as response:
        body = response.read().decode("utf-8", errors="replace")

    assert response.status == 200
    assert "Acquire" in body
