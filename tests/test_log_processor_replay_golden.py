import json
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "game_logs"
LOG_TIMESTAMP = 1780589302


pytestmark = pytest.mark.golden


def summarize_replayed_game(game):
    return {
        "log_timestamp": game.log_timestamp,
        "internal_game_id": game.internal_game_id,
        "external_game_id": game.game_id,
        "state": game.state,
        "mode": game.mode,
        "max_players": game.max_players,
        "begin": game.begin,
        "end": game.end,
        "expired": game.expired,
        "player_id_to_username": {
            str(key): value for key, value in sorted(game.player_id_to_username.items())
        },
        "username_to_player_id": game.username_to_player_id,
        "score": game.score,
        "played_tiles_count": len(game.played_tiles_order),
        "first_played_tiles": game.played_tiles_order[:5],
        "last_played_tiles": game.played_tiles_order[-5:],
        "history_count_by_user": {
            username: len(history)
            for username, history in sorted(game.username_to_game_history.items())
        },
    }


def test_log_processor_replays_redacted_real_server_log(logs_to_games_without_database):
    log_path = FIXTURES_DIR / "redacted_real_server.txt"
    expected_path = FIXTURES_DIR / "redacted_real_server.replay.expected.json"

    with log_path.open() as log_file:
        games = logs_to_games_without_database.LogProcessor(LOG_TIMESTAMP, log_file).go()
        actual = json.loads(json.dumps([summarize_replayed_game(game) for game in games]))

    with expected_path.open() as expected_file:
        expected = json.load(expected_file)

    assert actual == expected
