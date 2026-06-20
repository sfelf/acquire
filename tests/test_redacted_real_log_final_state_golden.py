import json
from pathlib import Path

import pytest

from enums import GameStates, ScoreSheetIndexes


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "game_logs"
LOG_TIMESTAMP = 1780589302
SEQUENCE_BOUNDARY_SIZE = 5


pytestmark = pytest.mark.golden


def compact_sequence(items, size=SEQUENCE_BOUNDARY_SIZE):
    return {
        "count": len(items),
        "first": items[:size],
        "last": items[-size:],
    }


def board_rows(game):
    return ["".join(str(game.board[x][y]) for x in range(12)) for y in range(9)]


def summarize_history(history):
    return {
        "count": len(history),
        "first": history[:3],
        "last": history[-3:],
    }


def summarize_actions(actions):
    normalized = [
        {"player_id": player_id, "action": action, "timestamp": timestamp}
        for player_id, action, timestamp in actions
    ]
    return compact_sequence(normalized)


def summarize_replayed_final_state(game):
    return {
        "internal_game_id": game.internal_game_id,
        "external_game_id": game.game_id,
        "state": game.state,
        "score": game.score,
        "board_rows": board_rows(game),
        "score_sheet_players": game.score_sheet_players[
            : len(game.player_id_to_username)
        ],
        "score_sheet_chain_size": game.score_sheet_chain_size,
        "initial_tile_racks": game.initial_tile_racks[
            : len(game.player_id_to_username)
        ],
        "final_tile_racks": game.tile_racks[: len(game.player_id_to_username)],
        "additional_tile_rack_tiles": compact_sequence(
            game.additional_tile_rack_tiles_order
        ),
        "actions": summarize_actions(game.actions),
        "history_by_user": {
            username: summarize_history(history)
            for username, history in sorted(game.username_to_game_history.items())
        },
    }


def summarize_server_sync(game):
    game.make_server_game()
    game.compare_with_server_game()
    net_index = ScoreSheetIndexes.Net.value
    num_players = len(game.player_id_to_username)
    rebuilt_history_counts = [0 for _ in range(num_players)]
    for target_player_id, _ in game.server_game.history_messages:
        if target_player_id is None:
            rebuilt_history_counts = [count + 1 for count in rebuilt_history_counts]
        elif target_player_id < num_players:
            rebuilt_history_counts[target_player_id] += 1

    return {
        "internal_game_id": game.internal_game_id,
        "external_game_id": game.game_id,
        "parsed_state": game.state,
        "rebuilt_state": GameStates(game.server_game.state).name,
        "expired": game.expired,
        "parsed_score": game.score,
        "rebuilt_score": [
            player_datum[net_index]
            for player_datum in game.server_game.score_sheet.player_data[:num_players]
        ],
        "action_count": len(game.actions),
        "played_tiles_count": len(game.played_tiles_order),
        "history_counts_by_player": [
            {
                "player_id": player_id,
                "username": username,
                "parsed": len(game.username_to_game_history[username]),
                "rebuilt": rebuilt_history_counts[player_id],
            }
            for player_id, username in sorted(game.player_id_to_username.items())
        ],
        "is_server_game_synchronized": game.is_server_game_synchronized,
        "sync_log": game.sync_log,
    }


def test_redacted_real_server_log_matches_final_state_golden(
    logs_to_games_without_database,
):
    log_path = FIXTURES_DIR / "redacted_real_server.txt"
    expected_path = FIXTURES_DIR / "redacted_real_server.final_state.expected.json"

    with log_path.open() as log_file:
        games = logs_to_games_without_database.LogProcessor(LOG_TIMESTAMP, log_file).go()
        actual = json.loads(
            json.dumps([summarize_replayed_final_state(game) for game in games])
        )

    with expected_path.open() as expected_file:
        expected = json.load(expected_file)

    assert actual == expected


def test_redacted_real_server_log_replays_against_server_game_golden(
    logs_to_games_without_database,
):
    log_path = FIXTURES_DIR / "redacted_real_server.txt"
    expected_path = FIXTURES_DIR / "redacted_real_server.sync.expected.json"

    with log_path.open() as log_file:
        games = logs_to_games_without_database.LogProcessor(LOG_TIMESTAMP, log_file).go()
        actual = json.loads(json.dumps([summarize_server_sync(game) for game in games]))

    with expected_path.open() as expected_file:
        expected = json.load(expected_file)

    assert actual == expected


def test_sample_server_log_matches_final_state_golden(logs_to_games_without_database):
    log_path = FIXTURES_DIR / "sample_server.txt"
    expected_path = FIXTURES_DIR / "sample_server.final_state.expected.json"

    with log_path.open() as log_file:
        games = logs_to_games_without_database.LogProcessor(1700000000, log_file).go()
        actual = json.loads(
            json.dumps([summarize_replayed_final_state(game) for game in games])
        )

    with expected_path.open() as expected_file:
        expected = json.load(expected_file)

    assert actual == expected
