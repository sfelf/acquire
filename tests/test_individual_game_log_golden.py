import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "game_logs"


def normalize_individual_game_log(game_log):
    return {
        "log_timestamp": game_log.log_timestamp,
        "internal_game_id": game_log.internal_game_id,
        "player_id_to_username": game_log.player_id_to_username,
        "username_to_player_id": game_log.username_to_player_id,
        "line_number_to_batch": game_log.line_number_to_batch,
    }


def test_individual_game_log_maker_matches_sample_golden_fixture(logs_to_games_without_database):
    log_path = FIXTURES_DIR / "sample_server.txt"
    expected_path = FIXTURES_DIR / "sample_individual_game.expected.json"

    with log_path.open() as log_file:
        game_logs = logs_to_games_without_database.IndividualGameLogMaker(1700000000, log_file).go()
        actual = json.loads(json.dumps([normalize_individual_game_log(game_log) for game_log in game_logs]))

    with expected_path.open() as expected_file:
        expected = json.load(expected_file)

    assert actual == expected
