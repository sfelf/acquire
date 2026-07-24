import json
import types

import pytest

from acquire import game_server as server
from acquire.enums import (
    CommandsToClient,
    GameActions,
    GameBoardTypes,
    GameHistoryMessages,
    GameModes,
    GameStates,
    ScoreSheetIndexes,
)

pytestmark = pytest.mark.unit


class RecordingClient:
    def __init__(self, client_id, username, player_id=None):
        self.client_id = client_id
        self.username = username
        self.player_id = player_id
        self.game_id = None


class RecordingAction:
    def __init__(self, player_id, game_action_id, execute_result=None, prepare_result=None):
        self.player_id = player_id
        self.game_action_id = game_action_id
        self.execute_result = execute_result
        self.prepare_result = prepare_result
        self.execute_calls = []
        self.prepare_calls = 0
        self.send_calls = []

    def execute(self, *data):
        self.execute_calls.append(data)
        return self.execute_result

    def prepare(self):
        self.prepare_calls += 1
        return self.prepare_result

    def send_message(self, client_ids):
        self.send_calls.append(client_ids)


def make_game(tile_bag=None, max_players=3):
    pending = []

    def add_pending_messages(messages, client_ids=None):
        pending.append((messages, client_ids))

    game = server.Game(
        "game-1",
        123,
        GameModes.Singles.value,
        max_players,
        add_pending_messages,
        logging_enabled=False,
        tile_bag=tile_bag or [(0, 0), (1, 1), (2, 2), (3, 3)],
    )
    return game, pending


def flatten_pending(pending):
    return [message for messages, _client_ids in pending for message in messages]


def test_join_game_adds_player_position_tile_history_and_start_action():
    game, pending = make_game()
    client = RecordingClient(10, "alice")

    game.join_game(client)

    assert game.num_players == 1
    assert client.game_id == "game-1"
    assert client.player_id == 0
    assert game.client_ids == {10}
    assert game.score_sheet.username_to_player_id == {"alice": 0}
    assert game.game_board.x_to_y_to_board_type[3][3] == GameBoardTypes.NothingYet.value
    assert game.history_messages == [
        [None, [GameHistoryMessages.DrewPositionTile.value, "alice", 3, 3]]
    ]
    assert len(game.actions) == 1
    assert isinstance(game.actions[0], server.ActionStartGame)
    assert game.actions[0].player_id == 0

    messages = flatten_pending(pending)
    assert [CommandsToClient.SetGamePlayerJoin.value, "game-1", 0, 10] in messages
    assert [
        CommandsToClient.SetGameBoardCell.value,
        3,
        3,
        GameBoardTypes.NothingYet.value,
    ] in messages
    assert [
        CommandsToClient.AddGameHistoryMessage.value,
        GameHistoryMessages.DrewPositionTile.value,
        0,
        3,
        3,
    ] in messages
    assert [CommandsToClient.SetGameAction.value, GameActions.StartGame.value, 0] in messages


def test_init_without_tile_bag_generates_and_shuffles_full_tile_set(monkeypatch):
    shuffled = []
    pending = []

    def shuffle(tiles):
        shuffled.append(list(tiles))
        tiles.reverse()

    monkeypatch.setattr(server.random, "shuffle", shuffle)
    game = server.Game(
        "game-1",
        123,
        GameModes.Singles.value,
        3,
        lambda messages, client_ids=None: pending.append((messages, client_ids)),
        logging_enabled=False,
    )

    assert len(shuffled) == 1
    assert shuffled[0][:3] == [(0, 0), (0, 1), (0, 2)]
    assert len(game.tile_bag) == 108
    assert len(set(game.tile_bag)) == 108
    assert game.tile_bag[0] == (11, 8)


def test_join_game_ignores_duplicate_username_and_non_starting_state():
    game, pending = make_game()
    player = RecordingClient(10, "alice")
    game.join_game(player)
    pending.clear()

    game.join_game(RecordingClient(11, "alice"))
    assert pending == []
    assert game.num_players == 1

    game.state = GameStates.InProgress.value
    game.join_game(RecordingClient(12, "bob"))

    assert pending == []
    assert game.num_players == 1


def test_watch_game_sends_initialization_history_and_action_without_joining():
    game, pending = make_game()
    player = RecordingClient(10, "alice")
    game.join_game(player)
    pending.clear()

    watcher = RecordingClient(20, "viewer")
    game.watch_game(watcher)

    assert watcher.game_id == "game-1"
    assert watcher.player_id is None
    assert game.client_ids == {10, 20}
    assert game.watcher_client_ids == {20}
    messages = flatten_pending(pending)
    assert [CommandsToClient.SetGameWatcherClientId.value, "game-1", 20] in messages
    assert [CommandsToClient.SetGameBoard.value, game.game_board.x_to_y_to_board_type] in messages
    assert [CommandsToClient.SetTurn.value, None] in messages
    assert [CommandsToClient.SetGameAction.value, GameActions.StartGame.value, 0] in messages
    assert [
        CommandsToClient.AddGameHistoryMessages.value,
        [[GameHistoryMessages.DrewPositionTile.value, 0, 3, 3]],
    ] in messages


def test_watch_game_ignores_username_already_in_game():
    game, pending = make_game()
    player = RecordingClient(10, "alice")
    game.join_game(player)
    pending.clear()

    game.watch_game(RecordingClient(20, "alice"))

    assert pending == []
    assert game.watcher_client_ids == set()


def test_rejoin_game_restores_player_client_and_initializes_state():
    game, pending = make_game()
    original = RecordingClient(10, "alice")
    game.join_game(original)
    game.leave_game(original)
    pending.clear()

    rejoining = RecordingClient(20, "alice")
    game.rejoin_game(rejoining)

    assert rejoining.game_id == "game-1"
    assert rejoining.player_id == 0
    assert game.client_ids == {20}
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Client.value] is rejoining
    messages = flatten_pending(pending)
    assert [CommandsToClient.SetGamePlayerRejoin.value, "game-1", 0, 20] in messages
    assert [CommandsToClient.SetGameBoard.value, game.game_board.x_to_y_to_board_type] in messages
    assert [CommandsToClient.SetTurn.value, None] in messages


def test_rejoin_game_ignores_unknown_username():
    game, pending = make_game()

    game.rejoin_game(RecordingClient(20, "alice"))

    assert pending == [
        ([[CommandsToClient.SetGameState.value, "game-1", 0, 0, 3]], None),
    ]


def test_leave_game_returns_watcher_to_lobby_without_touching_score_sheet():
    game, pending = make_game()
    watcher = RecordingClient(20, "viewer")
    game.client_ids.add(20)
    game.watcher_client_ids.add(20)

    game.leave_game(watcher)

    assert watcher.game_id is None
    assert game.client_ids == set()
    assert game.watcher_client_ids == set()
    assert game.expiration_time is not None
    assert pending == [
        ([[CommandsToClient.SetGameState.value, "game-1", 0, 0, 3]], None),
        ([[CommandsToClient.ReturnWatcherToLobby.value, "game-1", 20]], None),
    ]


def test_leave_game_clears_player_client_and_announces_missing_player():
    game, pending = make_game()
    player = RecordingClient(10, "alice")
    game.join_game(player)
    pending.clear()

    game.leave_game(player)

    assert player.game_id is None
    assert player.player_id is None
    assert game.client_ids == set()
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Client.value] is None
    assert game.expiration_time is not None
    assert pending == [
        ([[CommandsToClient.SetGamePlayerLeave.value, "game-1", 0, 10]], None),
    ]


def test_leave_game_ignores_client_not_in_game():
    game, pending = make_game()

    game.leave_game(RecordingClient(99, "visitor"))

    assert pending == [
        ([[CommandsToClient.SetGameState.value, "game-1", 0, 0, 3]], None),
    ]


def test_send_past_history_messages_filters_private_history_to_rejoining_player():
    game, pending = make_game()
    game.score_sheet.player_data = [
        [0, 0, 0, 0, 0, 0, 0, 60, 60, "alice", None, None],
        [0, 0, 0, 0, 0, 0, 0, 60, 60, "bob", None, None],
    ]
    game.score_sheet.username_to_player_id = {"alice": 0, "bob": 1}
    game.history_messages = [
        [None, [GameHistoryMessages.DrewPositionTile.value, "alice", 3, 3]],
        [0, [GameHistoryMessages.DrewTile.value, 0, 1, 1]],
        [1, [GameHistoryMessages.DrewTile.value, 1, 2, 2]],
    ]
    pending.clear()
    client = RecordingClient(10, "alice", player_id=0)

    game._send_past_history_messages(client)

    assert pending == [
        (
            [
                [
                    CommandsToClient.AddGameHistoryMessages.value,
                    [
                        [GameHistoryMessages.DrewPositionTile.value, 0, 3, 3],
                        [GameHistoryMessages.DrewTile.value, 0, 1, 1],
                    ],
                ]
            ],
            {10},
        )
    ]


def test_add_history_message_sends_private_string_message_to_connected_player():
    game, pending = make_game()
    client = RecordingClient(10, "alice", player_id=0)
    game.client_ids = {10}
    game.score_sheet.player_data = [
        [0, 0, 0, 0, 0, 0, 0, 60, 60, "alice", None, client],
    ]
    game.score_sheet.username_to_player_id = {"alice": 0}
    pending.clear()

    game.add_history_message(
        GameHistoryMessages.DrewPositionTile.value,
        "alice",
        1,
        2,
        player_id=0,
    )

    assert game.history_messages == [
        [0, [GameHistoryMessages.DrewPositionTile.value, "alice", 1, 2]]
    ]
    assert pending == [
        (
            [
                [
                    CommandsToClient.AddGameHistoryMessage.value,
                    GameHistoryMessages.DrewPositionTile.value,
                    0,
                    1,
                    2,
                ]
            ],
            {10},
        )
    ]


def test_add_history_message_records_private_message_for_disconnected_player():
    game, pending = make_game()
    game.score_sheet.player_data = [
        [0, 0, 0, 0, 0, 0, 0, 60, 60, "alice", None, None],
    ]
    pending.clear()

    game.add_history_message(GameHistoryMessages.DrewTile.value, 0, 1, 2, player_id=0)

    assert game.history_messages == [[0, [GameHistoryMessages.DrewTile.value, 0, 1, 2]]]
    assert pending == []


def test_send_initialization_messages_includes_player_tiles():
    game, pending = make_game()
    client = RecordingClient(10, "alice", player_id=0)
    game.tile_racks = types.SimpleNamespace(
        racks=[
            [[(1, 2), GameBoardTypes.Luxor.value, False], None, None, None, None, None],
        ]
    )
    game.actions = [RecordingAction(0, GameActions.PlayTile.value)]
    pending.clear()

    game._send_initialization_messages(client)

    assert flatten_pending(pending) == [
        [CommandsToClient.SetGameBoard.value, game.game_board.x_to_y_to_board_type],
        [CommandsToClient.SetScoreSheet.value, [[], [0, 0, 0, 0, 0, 0, 0]]],
        [CommandsToClient.SetTile.value, 0, 1, 2, GameBoardTypes.Luxor.value],
        [CommandsToClient.SetTurn.value, None],
    ]
    assert game.actions[0].send_calls == [{10}]


def test_do_game_action_ignores_wrong_player_or_action_id():
    game, _pending = make_game()
    action = RecordingAction(0, GameActions.PlayTile.value, execute_result=True)
    game.actions = [action]

    game.do_game_action(RecordingClient(10, "alice", player_id=1), GameActions.PlayTile.value, [0])
    game.do_game_action(
        RecordingClient(10, "alice", player_id=0), GameActions.PurchaseShares.value, [0]
    )

    assert action.execute_calls == []
    assert action.send_calls == []


def test_do_game_action_ignores_client_without_player_id():
    game, _pending = make_game()
    action = RecordingAction(0, GameActions.PlayTile.value, execute_result=True)
    game.actions = [action]

    game.do_game_action(
        RecordingClient(10, "watcher", player_id=None),
        GameActions.PlayTile.value,
        [0],
    )

    assert action.execute_calls == []
    assert action.send_calls == []


def test_do_game_action_replaces_completed_action_with_prepared_follow_up_actions():
    game, _pending = make_game()
    game.client_ids = {10, 11}
    follow_up = RecordingAction(1, GameActions.PurchaseShares.value)
    action = RecordingAction(
        0,
        GameActions.PlayTile.value,
        execute_result=[follow_up],
    )
    game.actions = [action]

    game.do_game_action(RecordingClient(10, "alice", player_id=0), GameActions.PlayTile.value, [2])

    assert action.execute_calls == [(2,)]
    assert follow_up.prepare_calls == 1
    assert follow_up.send_calls == [{10, 11}]
    assert game.actions == [follow_up]


def test_set_state_logs_overridden_completed_score(capsys):
    game, pending = make_game()
    game.logging_enabled = True
    game.log_data_overrides = {"log-time": 1234, "score": [99, 88]}
    game.score_sheet.player_data = [
        [0, 0, 0, 0, 0, 0, 0, 60, 75, "alice", None, None],
        [0, 0, 0, 0, 0, 0, 0, 60, 80, "bob", None, None],
    ]

    game.set_state(GameStates.Completed.value)

    log = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert log["state"] == "Completed"
    assert log["score"] == [99, 88]
    assert log["log-time"] == 1234
    assert log["used-log-data-overrides"] is True
    assert flatten_pending(pending)[-1] == [
        CommandsToClient.SetGameState.value,
        "game-1",
        GameStates.Completed.value,
        GameModes.Singles.value,
        3,
        [60, 60],
    ]


def test_set_state_sends_mode_when_only_mode_changes():
    game, pending = make_game()
    pending.clear()

    game.set_state(GameStates.InProgress.value, mode=GameModes.Teams.value)

    assert pending == [
        (
            [
                [
                    CommandsToClient.SetGameState.value,
                    "game-1",
                    GameStates.InProgress.value,
                    GameModes.Teams.value,
                ]
            ],
            None,
        )
    ]
