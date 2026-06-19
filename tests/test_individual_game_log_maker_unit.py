import io

import pytest
from enums import CommandsToClient, CommandsToServer


pytestmark = pytest.mark.unit


def make_maker(logs_to_games):
    return logs_to_games.IndividualGameLogMaker(1700000000, io.StringIO(""))


def test_individual_game_log_file_writes_sorted_batches(
    logs_to_games_without_database,
    tmp_path,
):
    game_log = logs_to_games_without_database.IndividualGameLog(1700000000, 77)
    game_log.line_number_to_batch = {
        10: ["10 <- [[1]]"],
        2: ["2 connect alice 127.0.0.1 socket-1 False"],
    }

    filename = tmp_path / "game.log"
    game_log.make_game_log_file(filename)

    assert filename.read_text().splitlines() == [
        "--- batch line number: 2",
        "2 connect alice 127.0.0.1 socket-1 False",
        "--- batch line number: 10",
        "10 <- [[1]]",
    ]


def test_individual_game_log_maker_attaches_prior_connect_batches(
    logs_to_games_without_database,
):
    maker = make_maker(logs_to_games_without_database)
    connect_batch = [
        "1 connect alice 127.0.0.1 socket-1 False",
        "1 disconnect",
    ]

    maker._handle_connect(1, "alice")
    maker._batch_completed(1, connect_batch)
    maker._handle_log({"_": "game", "game-id": 77, "external-game-id": 7})

    game_log = maker._game_id_to_game_log[7]
    assert game_log.line_number_to_batch == {
        1: ["1 connect alice 127.0.0.1 socket-1 False"],
    }


def test_individual_game_log_maker_records_game_batches_and_completion(
    logs_to_games_without_database,
):
    maker = make_maker(logs_to_games_without_database)
    maker._handle_connect(10, "alice")
    maker._handle_log({"_": "game", "game-id": 77, "external-game-id": 7})
    maker._handle_log(
        {
            "_": "game-player",
            "game-id": 77,
            "external-game-id": 7,
            "player-id": 0,
            "username": "alice",
        }
    )

    maker._handle_command_to_client__set_game_player_join(
        [],
        [CommandsToClient.SetGamePlayerJoin.value, 7, 0, 10],
    )
    maker._batch_completed(5, ["10 <- join"])
    maker._handle_command_to_server__do_game_action(
        10,
        [CommandsToServer.DoGameAction.value, 1, "payload"],
    )
    maker._batch_completed(6, ["10 -> action"])
    maker._handle_game_expired(7)
    maker._batch_completed(7, ["game #7 expired"])

    game_log = maker._completed_game_logs[0]
    assert game_log.player_id_to_username == {0: "alice"}
    assert game_log.username_to_player_id == {"alice": 0}
    assert game_log.line_number_to_batch[5] == ["10 <- join"]
    assert game_log.line_number_to_batch[6] == ["10 -> action"]
    assert 7 not in maker._game_id_to_game_log


def test_individual_game_log_maker_disconnect_removes_connect_batch(
    logs_to_games_without_database,
):
    maker = make_maker(logs_to_games_without_database)
    maker._handle_connect(10, "alice")
    maker._batch_completed(1, ["10 connect alice 127.0.0.1 socket-1 False"])
    maker._handle_log({"_": "game", "game-id": 77, "external-game-id": 7})

    maker._handle_disconnect__delayed(10)
    maker._batch_completed(2, ["10 disconnect"])

    game_log = maker._game_id_to_game_log[7]
    assert game_log.line_number_to_batch[2] == ["10 disconnect"]
    assert maker._client_id_to_add_batch == {}


def test_individual_game_log_maker_player_client_id_updates_membership(
    logs_to_games_without_database,
):
    maker = make_maker(logs_to_games_without_database)
    maker._handle_connect(10, "alice")
    maker._handle_connect(20, "bob")
    maker._handle_log({"_": "game", "game-id": 77, "external-game-id": 7})
    maker._handle_log(
        {
            "_": "game-player",
            "game-id": 77,
            "external-game-id": 7,
            "player-id": 1,
            "username": "bob",
        }
    )
    set_game_player_client_id = logs_to_games_without_database.Enums.lookups[
        "CommandsToClient"
    ].index("SetGamePlayerClientId")

    maker._handle_command_to_client__set_game_player_client_id(
        [],
        [set_game_player_client_id, 7, 1, 20],
    )
    maker._handle_command_to_client__set_game_player_client_id(
        [],
        [set_game_player_client_id, 7, 1, None],
    )

    assert maker._batch_game_id == 7
    assert 20 not in maker._client_id_to_game_id


def test_individual_game_log_maker_remove_helpers_ignore_unknown_ids(
    logs_to_games_without_database,
):
    maker = make_maker(logs_to_games_without_database)
    maker._handle_connect(10, "alice")
    maker._handle_log({"_": "game", "game-id": 77, "external-game-id": 7})
    maker._game_id_to_game_log[7].player_id_to_username[0] = "alice"

    maker._remove_client_id_from_game(99)
    maker._remove_player_id_from_game(7, 0)

    assert maker._batch_game_id is None


def test_individual_game_log_maker_command_handlers_continue_after_errors(
    logs_to_games_without_database,
    capsys,
):
    maker = make_maker(logs_to_games_without_database)

    def raise_error(*_args):
        raise RuntimeError("batch handler failed")

    maker._commands_to_client_handlers[CommandsToClient.SetTurn.value] = raise_error
    maker._commands_to_server_handlers[CommandsToServer.DoGameAction.value] = raise_error

    maker._handle_command_to_client(
        [10],
        [[CommandsToClient.SetTurn.value, 0]],
    )
    maker._handle_command_to_server(
        10,
        [CommandsToServer.DoGameAction.value, 1],
    )

    captured = capsys.readouterr()
    assert "RuntimeError: batch handler failed" in captured.err


def test_username_helpers_normalize_known_and_non_ascii_names(
    logs_to_games_without_database,
):
    assert logs_to_games_without_database.is_ascii("Alice_123")
    assert not logs_to_games_without_database.is_ascii("José")
    assert (
        logs_to_games_without_database.get_actual_username(1418805302, "Temp")
        == "Mr Brain"
    )
    assert logs_to_games_without_database.get_actual_username(1700000000, "José") == "Jos-dma"
