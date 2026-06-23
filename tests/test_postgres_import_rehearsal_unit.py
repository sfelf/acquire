import importlib

import pytest

pytestmark = pytest.mark.unit


def test_distinct_postgres_port_uses_fallback_when_probe_returns_same_port():
    rehearsal_module = importlib.import_module("test_postgres_import_rehearsal")

    assert rehearsal_module._distinct_postgres_port("35432", "35432") == "35433"


def test_distinct_postgres_port_preserves_distinct_probe_result():
    rehearsal_module = importlib.import_module("test_postgres_import_rehearsal")

    assert rehearsal_module._distinct_postgres_port("35432", "35434") == "35434"
