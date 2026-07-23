import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "game_logs"


pytestmark = pytest.mark.golden


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


def test_log_parser_matches_sample_golden_fixture(logs_to_games_without_database):
    log_path = FIXTURES_DIR / "sample_server.txt"
    expected_path = FIXTURES_DIR / "sample_server.expected.json"

    with log_path.open() as log_file:
        events = logs_to_games_without_database.LogParser(1700000000, log_file).go()
        actual = normalize_parser_events(events)

    with expected_path.open() as expected_file:
        expected = json.load(expected_file)

    assert actual == expected
