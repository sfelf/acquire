import importlib
import sys
import types
from pathlib import Path

import pytest


SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


@pytest.fixture
def logs_to_games_without_database(monkeypatch):
    monkeypatch.delitem(sys.modules, "logs_to_games", raising=False)

    sqlalchemy = types.ModuleType("sqlalchemy")
    sqlalchemy.sql = types.SimpleNamespace(text=lambda query: query)
    monkeypatch.setitem(sys.modules, "orm", types.ModuleType("orm"))
    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy)
    monkeypatch.setitem(sys.modules, "sqlalchemy.sql", sqlalchemy.sql)

    try:
        yield importlib.import_module("logs_to_games")
    finally:
        sys.modules.pop("logs_to_games", None)
