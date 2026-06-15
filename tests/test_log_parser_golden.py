import importlib
import json
import sys
import types
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "game_logs"


def import_logs_to_games_without_database(monkeypatch):
    monkeypatch.delitem(sys.modules, "logs_to_games", raising=False)

    sqlalchemy = types.ModuleType("sqlalchemy")
    sqlalchemy.sql = types.SimpleNamespace(text=lambda query: query)
    monkeypatch.setitem(sys.modules, "orm", types.ModuleType("orm"))
    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy)
    monkeypatch.setitem(sys.modules, "sqlalchemy.sql", sqlalchemy.sql)

    return importlib.import_module("logs_to_games")


def normalize_parser_events(events):
    normalized = []
    for line_type, line_number, _line, parse_line_data in events:
        normalized.append(
            {
                "line_number": line_number,
                "line_type": line_type.name,
                "parse_line_data": json.loads(json.dumps(parse_line_data)),
            }
        )
    return normalized


def test_log_parser_matches_sample_golden_fixture(monkeypatch, request):
    request.addfinalizer(lambda: sys.modules.pop("logs_to_games", None))
    logs_to_games = import_logs_to_games_without_database(monkeypatch)
    log_path = FIXTURES_DIR / "sample_server.txt"
    expected_path = FIXTURES_DIR / "sample_server.expected.json"

    with log_path.open() as log_file:
        events = logs_to_games.LogParser(1700000000, log_file).go()
        actual = normalize_parser_events(events)

    with expected_path.open() as expected_file:
        expected = json.load(expected_file)

    assert actual == expected
