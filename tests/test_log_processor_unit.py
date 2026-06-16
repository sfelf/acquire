import io
import pickle
import types

import pytest
from enums import CommandsToClient, CommandsToServer, GameBoardTypes, GameHistoryMessages


pytestmark = pytest.mark.unit


def make_processor(logs_to_games):
    return logs_to_games.LogProcessor(1700000000, io.StringIO(""))


def make_game(logs_to_games):
    game = logs_to_games.Game(1700000000, 7, 77, False)
    game.player_id_to_username = {0: "alice", 1: "bob"}
    game.username_to_player_id = {"alice": 0, "bob": 1}
    game.username_to_game_history = {"alice": [], "bob": []}
    return game


def attach_game(processor, game):
    processor._game_id_to_game[game.game_id] = game
    processor._client_id_to_username = {10: "alice", 20: "bob", 30: "watcher"}
    processor._username_to_client_id = {"alice": 10, "bob": 20, "watcher": 30}
    processor._client_id_to_game_id = {10: game.game_id, 20: game.game_id, 30: game.game_id}


def test_log_processor_tracks_connects_and_disconnects(logs_to_games_without_database):
    processor = make_processor(logs_to_games_without_database)

    processor._handle_connect(10, "alice")
    processor._handle_connect(20, "bob")
    processor._handle_disconnect(10)

    assert processor._client_id_to_username == {20: "bob"}
    assert processor._username_to_client_id == {"bob": 20}


def test_log_processor_ingests_game_and_player_log_entries(logs_to_games_without_database):
    processor = make_processor(logs_to_games_without_database)

    processor._handle_log(
        {
            "_": "game",
            "game-id": 77,
            "external-game-id": 7,
            "state": "Completed",
            "mode": "Singles",
            "max-players": 3,
            "tile-bag": [[0, 0], [1, 1]],
            "begin": 100,
            "end": 200,
            "scores": [90, 70],
        }
    )
    processor._handle_log(
        {
            "_": "game-player",
            "game-id": 77,
            "external-game-id": 7,
            "player-id": 0,
            "username": "alice",
        }
    )

    game = processor._game_id_to_game[7]
    assert game.internal_game_id == 77
    assert game.state == "Completed"
    assert game.mode == "Singles"
    assert game.max_players == 3
    assert game.tile_bag == [(0, 0), (1, 1)]
    assert game.begin == 100
    assert game.end == 200
    assert game.score == [90, 70]
    assert game.player_id_to_username == {0: "alice"}
    assert game.username_to_player_id == {"alice": 0}
    assert game.player_join_order == ["alice"]
    assert game.username_to_game_history == {"alice": []}


def test_log_processor_uses_begin_as_timestamp_when_no_time_seen(
    logs_to_games_without_database,
):
    processor = make_processor(logs_to_games_without_database)

    processor._handle_log({"_": "game", "game-id": 1, "begin": 123})

    assert processor._timestamp == 123


def test_log_processor_updates_board_and_removes_played_tile_from_rack(
    logs_to_games_without_database,
):
    processor = make_processor(logs_to_games_without_database)
    game = make_game(logs_to_games_without_database)
    game.tile_racks[0][0] = (2, 3)
    attach_game(processor, game)

    processor._handle_command_to_client__set_game_board_cell(
        [10], [CommandsToClient.SetGameBoardCell.value, 2, 3, GameBoardTypes.Luxor.value]
    )
    processor._handle_command_to_client__set_game_board_cell(
        [10], [CommandsToClient.SetGameBoardCell.value, 2, 3, GameBoardTypes.Tower.value]
    )

    assert game.board[2][3] == GameBoardTypes.Tower.value
    assert game.played_tiles_order == [(2, 3)]
    assert game.tile_racks[0][0] is None


def test_log_processor_updates_score_sheet_cells_and_full_sheet(
    logs_to_games_without_database,
):
    processor = make_processor(logs_to_games_without_database)
    game = make_game(logs_to_games_without_database)
    attach_game(processor, game)

    processor._handle_command_to_client__set_score_sheet_cell(
        [10], [CommandsToClient.SetScoreSheetCell.value, 0, 7, 75]
    )
    processor._handle_command_to_client__set_score_sheet_cell(
        [10], [CommandsToClient.SetScoreSheetCell.value, 6, 2, 11]
    )
    processor._handle_command_to_client__set_score_sheet(
        [
            10,
        ],
        [
            CommandsToClient.SetScoreSheet.value,
            [
                [[1, 2, 3, 4, 5, 6, 7, 80], [8, 7, 6, 5, 4, 3, 2, 70]],
                [1, 2, 3, 4, 5, 6, 7],
            ],
        ],
    )

    assert game.score_sheet_players[:2] == [
        [1, 2, 3, 4, 5, 6, 7, 80],
        [8, 7, 6, 5, 4, 3, 2, 70],
    ]
    assert game.score_sheet_chain_size == [1, 2, 3, 4, 5, 6, 7]


def test_log_processor_tracks_client_game_membership(logs_to_games_without_database):
    processor = make_processor(logs_to_games_without_database)
    game = make_game(logs_to_games_without_database)
    processor._game_id_to_game[game.game_id] = game
    processor._username_to_client_id = {"alice": 10}

    processor._handle_command_to_client__set_game_player_join(
        [], [CommandsToClient.SetGamePlayerJoin.value, game.game_id, 0, 10]
    )
    processor._handle_command_to_client__set_game_player_rejoin(
        [], [CommandsToClient.SetGamePlayerRejoin.value, game.game_id, 0, 20]
    )
    processor._handle_command_to_client__set_game_watcher_client_id(
        [], [CommandsToClient.SetGameWatcherClientId.value, game.game_id, 30]
    )
    processor._handle_command_to_client__set_game_player_leave(
        [], [CommandsToClient.SetGamePlayerLeave.value, game.game_id, 0, 20]
    )
    set_game_player_client_id = logs_to_games_without_database.Enums.lookups[
        "CommandsToClient"
    ].index("SetGamePlayerClientId")
    processor._handle_command_to_client__set_game_player_client_id(
        [], [set_game_player_client_id, game.game_id, 0, None]
    )
    processor._handle_command_to_client__return_watcher_to_lobby(
        [], [CommandsToClient.ReturnWatcherToLobby.value, game.game_id, 30]
    )

    assert processor._client_id_to_game_id == {}


def test_log_processor_records_history_for_players_only(logs_to_games_without_database):
    processor = make_processor(logs_to_games_without_database)
    game = make_game(logs_to_games_without_database)
    attach_game(processor, game)

    processor._handle_command_to_client__add_game_history_message(
        [10, 30],
        [
            CommandsToClient.AddGameHistoryMessage.value,
            GameHistoryMessages.DrewPositionTile.value,
            0,
            1,
            2,
        ],
    )
    processor._handle_command_to_client__add_game_history_messages(
        [20],
        [
            CommandsToClient.AddGameHistoryMessages.value,
            [
                [GameHistoryMessages.TurnBegan.value, 1],
                [GameHistoryMessages.PlayedTile.value, 1, 3, 4],
            ],
        ],
    )

    assert game.username_to_game_history == {
        "alice": [[GameHistoryMessages.DrewPositionTile.value, "alice", 1, 2]],
        "bob": [
            [GameHistoryMessages.TurnBegan.value, 1],
            [GameHistoryMessages.PlayedTile.value, 1, 3, 4],
        ],
    }


def test_log_processor_tracks_tile_racks(logs_to_games_without_database):
    processor = make_processor(logs_to_games_without_database)
    game = make_game(logs_to_games_without_database)
    attach_game(processor, game)

    processor._handle_command_to_client__set_tile(
        [10], [CommandsToClient.SetTile.value, 0, 1, 2]
    )
    processor._handle_command_to_client__set_tile(
        [10], [CommandsToClient.SetTile.value, 1, 3, 4]
    )
    processor._handle_command_to_client__set_tile(
        [10], [CommandsToClient.SetTile.value, 0, 1, 2]
    )
    processor._handle_command_to_client__set_tile(
        [10], [CommandsToClient.SetTile.value, 1, 5, 6]
    )
    processor._handle_command_to_client__remove_tile(
        [10], [CommandsToClient.RemoveTile.value, 1]
    )

    assert game.initial_tile_racks[0][:2] == [(1, 2), (3, 4)]
    assert game.tile_racks[0][:2] == [(1, 2), None]
    assert game.tile_rack_tiles == {(1, 2), (3, 4), (5, 6)}
    assert game.additional_tile_rack_tiles_order == [(5, 6)]


def test_log_processor_records_player_actions_with_timestamp(
    logs_to_games_without_database,
):
    processor = make_processor(logs_to_games_without_database)
    game = make_game(logs_to_games_without_database)
    attach_game(processor, game)
    processor._handle_time(123.5)

    processor._handle_command_to_server__do_game_action(
        10, [CommandsToServer.DoGameAction.value, 1, "payload"]
    )
    processor._handle_command_to_server__do_game_action(
        30, [CommandsToServer.DoGameAction.value, 2, "ignored"]
    )
    processor._handle_blank_line()

    assert game.actions == [
        [0, [1, "payload"], 123.5],
    ]
    assert processor._timestamp is None


def test_log_processor_expires_games(logs_to_games_without_database):
    processor = make_processor(logs_to_games_without_database)
    game = make_game(logs_to_games_without_database)
    processor._game_id_to_game[game.game_id] = game

    processor._handle_game_expired(game.game_id)

    assert game.expired is True
    assert processor._expired_games == [game]
    assert processor._game_id_to_game == {}


def test_game_translates_drew_position_tile_player_id(logs_to_games_without_database):
    game = make_game(logs_to_games_without_database)

    assert game.translate_add_game_history_message(
        [GameHistoryMessages.DrewPositionTile.value, 0, 1, 2]
    ) == [GameHistoryMessages.DrewPositionTile.value, "alice", 1, 2]
    assert game.translate_add_game_history_message(
        [GameHistoryMessages.DrewTile.value, 0, 3, 4]
    ) == [GameHistoryMessages.DrewTile.value, 0, 3, 4]


def test_game_initial_tile_bag_prefers_explicit_tile_bag(logs_to_games_without_database):
    game = make_game(logs_to_games_without_database)
    game.tile_bag = [(0, 0), (1, 1)]

    tile_bag = game._get_initial_tile_bag()

    assert tile_bag == [(0, 0), (1, 1)]
    assert tile_bag is not game.tile_bag


def test_game_initial_tile_bag_is_derived_from_history(logs_to_games_without_database):
    game = make_game(logs_to_games_without_database)
    game.username_to_game_history = {
        "alice": [
            [GameHistoryMessages.DrewTile.value, 0, 0, 0],
            [GameHistoryMessages.DrewTile.value, 0, 1, 1],
            [GameHistoryMessages.TurnBegan.value, 0],
            [GameHistoryMessages.ReplacedDeadTile.value, 0, 2, 2],
        ],
        "bob": [
            [GameHistoryMessages.DrewTile.value, 1, 3, 3],
            [GameHistoryMessages.TurnBegan.value, 1],
            [GameHistoryMessages.DrewTile.value, 1, 4, 4],
        ],
    }

    tile_bag = game._get_initial_tile_bag()

    assert tile_bag[-5:] == [(4, 4), (2, 2), (3, 3), (1, 1), (0, 0)]
    assert len(tile_bag) == 108
    assert len(set(tile_bag)) == 108


def test_game_sync_compare_records_diffs(logs_to_games_without_database):
    game = make_game(logs_to_games_without_database)
    game.is_server_game_synchronized = True
    game.sync_log = []

    game._sync_compare("board", [[1]], [[2]])
    game._sync_compare("tile_racks", [[(0, 0)], [(1, 1)]], [[(0, 0)], [None]])

    assert game.is_server_game_synchronized is False
    assert game.sync_log == [
        "board diff!",
        "[[1]]",
        "[[2]]",
        "tile_racks diff for player_id 1!",
        "[(1, 1)]",
        "[None]",
    ]


def test_game_make_server_game_file_serializes_snapshot(
    logs_to_games_without_database,
    tmp_path,
):
    game = make_game(logs_to_games_without_database)
    game.begin = 100
    game.end = 200
    action = types.SimpleNamespace(game=object(), player_id=0, game_action_id=1)
    game.server_game = types.SimpleNamespace(
        game_id=7,
        internal_game_id=77,
        state=1,
        mode=2,
        max_players=3,
        num_players=2,
        tile_bag=[(0, 0)],
        turn_player_id=0,
        turns_without_played_tiles_count=1,
        history_messages=[(None, [GameHistoryMessages.TurnBegan.value, 0])],
        game_board=types.SimpleNamespace(x_to_y_to_board_type=[[0]]),
        score_sheet=types.SimpleNamespace(
            player_data=[
                [0, 0, 0, 0, 0, 0, 0, 60, 60, "alice", None],
                [0, 0, 0, 0, 0, 0, 0, 60, 60, "bob", None],
            ],
            available=[25] * 7,
            chain_size=[0] * 7,
            price=[0] * 7,
            creator_username="alice",
            username_to_player_id={"alice": 0, "bob": 1},
        ),
        tile_racks=types.SimpleNamespace(racks=[[(0, 0)], [(1, 1)]]),
        actions=[action],
    )
    filename = tmp_path / "game.bin"

    game.make_server_game_file(filename)

    with filename.open("rb") as file:
        data = pickle.load(file)

    assert data["game_id"] == 7
    assert data["internal_game_id"] == 77
    assert data["score_sheet"]["player_data"] == [
        [0, 0, 0, 0, 0, 0, 0, 60, 60, "alice", None, None],
        [0, 0, 0, 0, 0, 0, 0, 60, 60, "bob", None, None],
    ]
    assert data["tile_racks"] == [[(0, 0)], [(1, 1)]]
    assert data["actions"] == [
        {"player_id": 0, "game_action_id": 1, "__name__": "SimpleNamespace"}
    ]
    assert data["log_time"] == 1700000000
    assert data["begin"] == 100
    assert data["end"] == 200
