import io
import pickle
import types

import pytest

from acquire.enums import CommandsToClient, CommandsToServer, GameBoardTypes, GameHistoryMessages

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


def test_log_processor_prints_verbose_history_batches(logs_to_games_without_database, capsys):
    processor = logs_to_games_without_database.LogProcessor(1700000000, io.StringIO(""), True)
    game = make_game(logs_to_games_without_database)
    attach_game(processor, game)

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

    output = capsys.readouterr().out
    assert "TurnBegan" in output
    assert "PlayedTile" in output


def test_log_processor_tracks_tile_racks(logs_to_games_without_database):
    processor = make_processor(logs_to_games_without_database)
    game = make_game(logs_to_games_without_database)
    attach_game(processor, game)

    processor._handle_command_to_client__set_tile([10], [CommandsToClient.SetTile.value, 0, 1, 2])
    processor._handle_command_to_client__set_tile([10], [CommandsToClient.SetTile.value, 1, 3, 4])
    processor._handle_command_to_client__set_tile([10], [CommandsToClient.SetTile.value, 0, 1, 2])
    processor._handle_command_to_client__set_tile([10], [CommandsToClient.SetTile.value, 1, 5, 6])
    processor._handle_command_to_client__remove_tile([10], [CommandsToClient.RemoveTile.value, 1])

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


def test_game_initial_tile_bag_applies_verbose_tweaks(
    logs_to_games_without_database,
    monkeypatch,
    capsys,
):
    game = make_game(logs_to_games_without_database)
    game._verbose = True
    game.username_to_game_history = {
        "alice": [[GameHistoryMessages.DrewTile.value, 0, 0, 0]],
        "bob": [[GameHistoryMessages.DrewTile.value, 1, 1, 1]],
    }
    monkeypatch.setattr(
        logs_to_games_without_database.Game,
        "tile_bag_tweaks",
        {(1700000000, 77): [[1, (2, 2)], [2, None]]},
    )
    monkeypatch.setattr(
        logs_to_games_without_database.random,
        "sample",
        lambda population, count: [(3, 3)],
    )

    tile_bag = game._get_initial_tile_bag()

    assert tile_bag[-4:] == [(1, 1), (3, 3), (2, 2), (0, 0)]
    assert len(tile_bag) == 108
    assert "specified tile for insertion: (2, 2)" in capsys.readouterr().out


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


def make_server_game_snapshot(tile_racks=True):
    return types.SimpleNamespace(
        game_board=types.SimpleNamespace(
            x_to_y_to_board_type=[
                [GameBoardTypes.Nothing.value for _y in range(9)] for _x in range(12)
            ]
        ),
        score_sheet=types.SimpleNamespace(
            player_data=[
                [1, 0, 0, 0, 0, 0, 0, 61],
                [0, 1, 0, 0, 0, 0, 0, 62],
            ],
            chain_size=[2, 0, 0, 0, 0, 0, 0],
            username_to_player_id={"alice": 0, "bob": 1},
        ),
        tile_racks=types.SimpleNamespace(
            racks=[
                [[(0, 0), 1], None, None, None, None, None],
                [[(1, 1), 1], None, None, None, None, None],
            ],
        )
        if tile_racks
        else None,
        history_messages=[
            [None, [GameHistoryMessages.StartedGame.value, 0]],
            [1, [GameHistoryMessages.DrewTile.value, 1, 1, 1]],
        ],
    )


def test_game_compare_with_server_game_marks_matching_snapshot_synchronized(
    logs_to_games_without_database,
):
    game = make_game(logs_to_games_without_database)
    game.score_sheet_players[0] = [1, 0, 0, 0, 0, 0, 0, 61]
    game.score_sheet_players[1] = [0, 1, 0, 0, 0, 0, 0, 62]
    game.score_sheet_chain_size = [2, 0, 0, 0, 0, 0, 0]
    game.tile_racks[0][0] = (0, 0)
    game.tile_racks[1][0] = (1, 1)
    game.username_to_game_history = {
        "alice": [[GameHistoryMessages.StartedGame.value, 0]],
        "bob": [
            [GameHistoryMessages.StartedGame.value, 0],
            [GameHistoryMessages.DrewTile.value, 1, 1, 1],
        ],
    }
    game.server_game = make_server_game_snapshot()

    game.compare_with_server_game()

    assert game.is_server_game_synchronized is True
    assert game.sync_log == []


def test_game_compare_with_server_game_reports_history_mismatch_verbose(
    logs_to_games_without_database,
):
    game = make_game(logs_to_games_without_database)
    game._verbose = True
    game.score_sheet_players[0] = [1, 0, 0, 0, 0, 0, 0, 61]
    game.score_sheet_players[1] = [0, 1, 0, 0, 0, 0, 0, 62]
    game.score_sheet_chain_size = [2, 0, 0, 0, 0, 0, 0]
    game.username_to_game_history = {
        "alice": [[GameHistoryMessages.StartedGame.value, 0]],
        "bob": [[GameHistoryMessages.DrewTile.value, 1, 1, 1]],
    }
    game.server_game = make_server_game_snapshot(tile_racks=False)

    game.compare_with_server_game()

    assert game.is_server_game_synchronized is False
    assert "player_id_to_game_history:" in game.sync_log
    assert "player_id_to_game_history diff for player_id 1!" in game.sync_log


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
    assert data["actions"] == [{"player_id": 0, "game_action_id": 1, "__name__": "SimpleNamespace"}]
    assert data["log_time"] == 1700000000
    assert data["begin"] == 100
    assert data["end"] == 200


def test_game_make_server_game_replays_joins_and_ignores_action_errors(
    logs_to_games_without_database,
    monkeypatch,
):
    game = make_game(logs_to_games_without_database)
    game.mode = "Singles"
    game.max_players = 2
    game.player_join_order = ["alice", "bob"]
    game.actions = [
        [0, [CommandsToServer.DoGameAction.value, "ok"], 10],
        [1, [CommandsToServer.DoGameAction.value, "boom"], 11],
    ]
    monkeypatch.setattr(game, "_get_initial_tile_bag", lambda: [(0, 0), (1, 1)])

    class FakeServerGame:
        def __init__(self, game_id, internal_game_id, mode, max_players, add, logging, bag):
            self.game_id = game_id
            self.internal_game_id = internal_game_id
            self.mode = mode
            self.max_players = max_players
            self.tile_bag = bag
            self.joined = []
            self.actions = []

        def join_game(self, client):
            client.player_id = len(self.joined)
            self.joined.append((client.client_id, client.username))

        def do_game_action(self, client, game_action_id, data):
            self.actions.append((client.username, game_action_id, data))
            if data == ["boom"]:
                raise RuntimeError("legacy replay mismatch")

    monkeypatch.setattr(
        logs_to_games_without_database.server,
        "Game",
        FakeServerGame,
    )

    game.make_server_game()

    assert game.server_game.joined == [(1, "alice"), (2, "bob")]
    assert game.server_game.actions == [
        ("alice", CommandsToServer.DoGameAction.value, ["ok"]),
        ("bob", CommandsToServer.DoGameAction.value, ["boom"]),
    ]


def test_log_processor_verbose_blank_line_writes_server_game_snapshot(
    logs_to_games_without_database,
    tmp_path,
    capsys,
):
    processor = logs_to_games_without_database.LogProcessor(
        1700000000,
        io.StringIO(""),
        verbose=True,
        verbose_output_path=str(tmp_path),
    )
    game = make_game(logs_to_games_without_database)
    game.make_server_game = lambda: None
    game.compare_with_server_game = lambda: None
    game.is_server_game_synchronized = True
    game.sync_log = ["sync detail"]
    written = []
    game.make_server_game_file = lambda filename: written.append(filename)
    processor._line_number = 42
    processor._game_id_to_game[game.game_id] = game

    processor._handle_blank_line()

    assert written == [str(tmp_path / "1700000000_00077_000042.bin")]
    output = capsys.readouterr().out
    assert "sync detail" in output
    assert "1700000000 77 42 yay!" in output


def test_log_processor_verbose_command_handlers_continue_after_errors(
    logs_to_games_without_database,
    capsys,
):
    processor = logs_to_games_without_database.LogProcessor(
        1700000000,
        io.StringIO(""),
        verbose=True,
    )
    processor._client_id_to_username = {10: "alice"}

    def raise_error(*_args):
        raise RuntimeError("handler failed")

    processor._commands_to_client_handlers[CommandsToClient.SetTurn.value] = raise_error
    processor._commands_to_server_handlers[CommandsToServer.DoGameAction.value] = raise_error

    processor._handle_command_to_client(
        [10],
        [[CommandsToClient.SetTurn.value, 0]],
    )
    processor._handle_command_to_server(
        10,
        [CommandsToServer.DoGameAction.value, 1],
    )

    captured = capsys.readouterr()
    assert "~~~ ['alice']" in captured.out
    assert "~~~ alice" in captured.out
    assert "RuntimeError: handler failed" in captured.err


def test_log_processor_disconnect_reports_duplicate_username_map(
    logs_to_games_without_database,
    capsys,
):
    processor = make_processor(logs_to_games_without_database)
    processor._client_id_to_username = {10: "alice", 20: "alice", 30: "bob"}
    processor._username_to_client_id = {"alice": 20, "bob": 30}

    processor._handle_disconnect(30)

    assert "remove_client: huh?" in capsys.readouterr().out
