import collections
import json
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "game_logs"
LOG_TIMESTAMP = 1780589302


pytestmark = pytest.mark.golden


def summarize_real_log_fixture(logs_to_games, log_path):
    with log_path.open() as log_file:
        events = list(logs_to_games.LogParser(LOG_TIMESTAMP, log_file).go())
    event_counts = collections.Counter(
        event[0].name if event[0] else "unhandled" for event in events
    )

    with log_path.open() as log_file:
        game_logs = list(logs_to_games.IndividualGameLogMaker(LOG_TIMESTAMP, log_file).go())

    game_log_summaries = []
    for game_log in game_logs:
        line_numbers = sorted(game_log.line_number_to_batch)
        game_log_summaries.append(
            {
                "log_timestamp": game_log.log_timestamp,
                "internal_game_id": game_log.internal_game_id,
                "batch_count": len(game_log.line_number_to_batch),
                "first_batch_line": line_numbers[0] if line_numbers else None,
                "last_batch_line": line_numbers[-1] if line_numbers else None,
                "player_id_to_username": {
                    str(key): value
                    for key, value in sorted(game_log.player_id_to_username.items())
                },
            }
        )

    return {
        "line_count": sum(1 for _ in log_path.open()),
        "parser_event_count": len(events),
        "parser_event_counts": dict(sorted(event_counts.items())),
        "individual_game_log_count": len(game_logs),
        "individual_game_logs": game_log_summaries,
    }


def test_redacted_real_server_log_matches_summary_golden(logs_to_games_without_database):
    log_path = FIXTURES_DIR / "redacted_real_server.txt"
    expected_path = FIXTURES_DIR / "redacted_real_server.summary.expected.json"

    actual = summarize_real_log_fixture(logs_to_games_without_database, log_path)

    with expected_path.open() as expected_file:
        expected = json.load(expected_file)

    assert actual == expected
