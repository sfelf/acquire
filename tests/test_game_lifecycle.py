import pytest
import server
from enums import CommandsToClient, GameActions, GameBoardTypes, GameHistoryMessages, GameModes


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
    assert [CommandsToClient.SetGameBoardCell.value, 3, 3, GameBoardTypes.NothingYet.value] in messages
    assert [CommandsToClient.AddGameHistoryMessage.value, GameHistoryMessages.DrewPositionTile.value, 0, 3, 3] in messages
    assert [CommandsToClient.SetGameAction.value, GameActions.StartGame.value, 0] in messages


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


def test_do_game_action_ignores_wrong_player_or_action_id():
    game, _pending = make_game()
    action = RecordingAction(0, GameActions.PlayTile.value, execute_result=True)
    game.actions = [action]

    game.do_game_action(RecordingClient(10, "alice", player_id=1), GameActions.PlayTile.value, [0])
    game.do_game_action(RecordingClient(10, "alice", player_id=0), GameActions.PurchaseShares.value, [0])

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
