import pytest
import ujson
from enums import (
    CommandsToClient,
    CommandsToServer,
    Errors,
    GameModes,
    GameStates,
)

import server

pytestmark = pytest.mark.unit


class ExpiringGame:
    def __init__(self, game_id, internal_game_id, expiration_time):
        self.game_id = game_id
        self.internal_game_id = internal_game_id
        self.expiration_time = expiration_time


class GameWithClients:
    def __init__(self, client_ids):
        self.client_ids = client_ids


class SnapshotGame:
    def __init__(self, game_id, internal_game_id, connected_client):
        self.game_id = game_id
        self.internal_game_id = internal_game_id
        self.state = GameStates.InProgress.value
        self.mode = GameModes.Singles.value
        self.max_players = 3
        self.watcher_client_ids = {99}
        self.score_sheet = type("ScoreSheet", (), {})()
        self.score_sheet.player_data = [
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "alice", None, connected_client],
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "bob", None, None],
        ]


class RecordingGame:
    def __init__(self):
        self.calls = []
        self.client_ids = {10, 20}

    def join_game(self, client):
        self.calls.append(("join", client.client_id))
        client.game_id = 7

    def rejoin_game(self, client):
        self.calls.append(("rejoin", client.client_id))
        client.game_id = 7

    def watch_game(self, client):
        self.calls.append(("watch", client.client_id))
        client.game_id = 7

    def leave_game(self, client):
        self.calls.append(("leave", client.client_id))
        client.game_id = None

    def do_game_action(self, client, game_action_id, data):
        self.calls.append(("action", client.client_id, game_action_id, data))


def make_client(username="alice", socket_id="socket-1"):
    writes = []
    game_server = server.Server()
    game_server.transport_write = writes.append
    client = server.Client(game_server, username, "127.0.0.1", socket_id, False)
    writes.clear()
    game_server.client_ids_and_messages.clear()
    return game_server, client, writes


def decode_write(write):
    _client_ids, messages = write.decode().strip().split(" ", 1)
    return ujson.decode(messages)


def decode_all_written_messages(write):
    messages = []
    for line in write.decode().splitlines():
        _client_ids, payload = line.split(" ", 1)
        messages.extend(ujson.decode(payload))
    return messages


def test_destroy_expired_games_removes_games_returns_ids_and_broadcasts(monkeypatch):
    writes = []
    game_server = server.Server()
    game_server.transport_write = writes.append
    game_server.client_ids = {10, 20}
    monkeypatch.setattr(server.time, "time", lambda: 1000)
    expired_game_id = game_server.next_game_id_manager.get_id()
    active_game_id = game_server.next_game_id_manager.get_id()
    expired_internal_id = game_server.next_internal_game_id_manager.get_id()
    active_internal_id = game_server.next_internal_game_id_manager.get_id()
    expired_game = ExpiringGame(expired_game_id, expired_internal_id, 999)
    active_game = ExpiringGame(active_game_id, active_internal_id, 1001)
    game_server.game_id_to_game = {
        expired_game_id: expired_game,
        active_game_id: active_game,
    }

    game_server.destroy_expired_games()

    assert game_server.game_id_to_game == {active_game_id: active_game}
    assert game_server.next_game_id_manager._used == {active_game_id}
    assert writes == [
        b"10,20 [[23,1]]\n",
    ]


def test_destroy_expired_games_does_nothing_without_expired_games(monkeypatch):
    writes = []
    game_server = server.Server()
    game_server.transport_write = writes.append
    monkeypatch.setattr(server.time, "time", lambda: 1000)
    active_game_id = game_server.next_game_id_manager.get_id()
    active_internal_id = game_server.next_internal_game_id_manager.get_id()
    active_game = ExpiringGame(active_game_id, active_internal_id, 1001)
    game_server.game_id_to_game = {active_game_id: active_game}

    game_server.destroy_expired_games()

    assert game_server.game_id_to_game == {active_game_id: active_game}
    assert writes == []


def test_client_global_chat_message_squashes_whitespace_and_broadcasts():
    game_server, client, _writes = make_client()

    client._on_message_send_global_chat_message("  hello   acquire table  ")

    assert game_server.client_ids_and_messages == [
        [
            {client.client_id},
            [
                [
                    CommandsToClient.AddGlobalChatMessage.value,
                    client.client_id,
                    "hello acquire table",
                ]
            ],
        ]
    ]


def test_client_global_chat_message_ignores_blank_after_normalization():
    game_server, client, _writes = make_client()

    client._on_message_send_global_chat_message(" \t\n ")

    assert game_server.client_ids_and_messages == []


def test_client_game_chat_message_sends_only_to_game_clients():
    game_server, client, _writes = make_client()
    client.game_id = 7
    game_server.game_id_to_game[7] = GameWithClients({client.client_id, 22})

    client._on_message_send_game_chat_message("  ready   when you are  ")

    assert game_server.client_ids_and_messages == [
        [
            {client.client_id, 22},
            [
                [
                    CommandsToClient.AddGameChatMessage.value,
                    client.client_id,
                    "ready when you are",
                ]
            ],
        ]
    ]


def test_client_on_message_routes_command_and_flushes_pending_messages():
    game_server, client, writes = make_client()
    payload = ujson.dumps(
        [CommandsToServer.SendGlobalChatMessage.value, "  hello   lobby  "]
    ).encode()

    client.on_message(payload)

    assert decode_write(writes[-1]) == [
        [CommandsToClient.AddGlobalChatMessage.value, client.client_id, "hello lobby"]
    ]
    assert game_server.client_ids_and_messages == []


def test_client_on_message_disconnects_on_malformed_payload():
    game_server, client, writes = make_client()

    client.on_message(b"not json")

    assert client.client_id not in game_server.client_id_to_client
    assert client.client_id not in game_server.client_ids
    assert client.username not in game_server.username_to_client
    assert writes[-2:] == [
        b"disconnect 1\n",
        b"",
    ]


def test_duplicate_username_without_replace_gets_fatal_error_and_disconnects():
    game_server, _first_client, writes = make_client("alice", "socket-1")

    duplicate = server.Client(game_server, "alice", "127.0.0.2", "socket-2", False)

    assert duplicate.client_id not in game_server.client_id_to_client
    assert writes[-3:] == [
        b'connect ["socket-2",2]\n',
        (b"2 [[0," + str(Errors.UsernameAlreadyInUse.value).encode() + b"]]\n"),
        b"disconnect 2\n",
    ]


def test_client_connect_snapshot_includes_other_clients_and_existing_games():
    writes = []
    game_server = server.Server()
    game_server.transport_write = writes.append
    alice = server.Client(game_server, "alice", "127.0.0.1", "socket-1", False)
    writes.clear()
    game_server.client_ids_and_messages.clear()
    game_server.game_id_to_game[7] = SnapshotGame(7, 12, alice)

    viewer = server.Client(game_server, "viewer", "127.0.0.3", "socket-3", False)

    assert viewer.client_id == 2
    assert writes[0] == b'connect ["socket-3",2]\n'
    messages = decode_all_written_messages(writes[1])
    assert [CommandsToClient.SetClientId.value, 2] in messages
    assert [
        CommandsToClient.SetClientIdToData.value,
        alice.client_id,
        "alice",
        "127.0.0.1",
    ] in messages
    assert [
        CommandsToClient.SetClientIdToData.value,
        viewer.client_id,
        "viewer",
        "127.0.0.3",
    ] in messages
    assert [
        CommandsToClient.SetGameState.value,
        7,
        GameStates.InProgress.value,
        GameModes.Singles.value,
        3,
    ] in messages
    assert [CommandsToClient.SetGamePlayerJoin.value, 7, 0, alice.client_id] in messages
    assert [CommandsToClient.SetGamePlayerJoinMissing.value, 7, 1, "bob"] in messages
    assert [CommandsToClient.SetGameWatcherClientId.value, 7, 99] in messages


def test_duplicate_username_with_replace_disconnects_old_client_and_logs_in_new_client():
    game_server, first_client, writes = make_client("alice", "socket-1")

    replacement = server.Client(game_server, "alice", "127.0.0.2", "socket-2", True)

    assert first_client.client_id not in game_server.client_id_to_client
    assert game_server.username_to_client == {"alice": replacement}
    assert replacement.client_id in game_server.client_ids
    assert writes[:2] == [
        b"disconnect 1\n",
        b"",
    ]
    assert writes[2] == b'connect ["socket-2",2]\n'


@pytest.mark.parametrize(
    ("method_name", "expected_call"),
    [
        ("_on_message_join_game", ("join", 1)),
        ("_on_message_rejoin_game", ("rejoin", 1)),
        ("_on_message_watch_game", ("watch", 1)),
    ],
)
def test_client_game_membership_commands_forward_to_existing_game(
    method_name,
    expected_call,
):
    game_server, client, _writes = make_client()
    game = RecordingGame()
    game_server.game_id_to_game[7] = game

    getattr(client, method_name)(7)

    assert game.calls == [expected_call]
    assert client.game_id == 7


@pytest.mark.parametrize(
    "method_name",
    [
        "_on_message_join_game",
        "_on_message_rejoin_game",
        "_on_message_watch_game",
    ],
)
def test_client_game_membership_commands_ignore_missing_or_busy_games(method_name):
    game_server, client, _writes = make_client()
    game = RecordingGame()
    game_server.game_id_to_game[7] = game

    getattr(client, method_name)(99)
    client.game_id = 7
    getattr(client, method_name)(7)

    assert game.calls == []


def test_client_leave_game_forwards_to_current_game():
    game_server, client, _writes = make_client()
    game = RecordingGame()
    game_server.game_id_to_game[7] = game
    client.game_id = 7

    client._on_message_leave_game()

    assert game.calls == [("leave", client.client_id)]
    assert client.game_id is None


def test_client_leave_game_ignores_client_outside_game():
    game_server, client, _writes = make_client()
    game = RecordingGame()
    game_server.game_id_to_game[7] = game

    client._on_message_leave_game()

    assert game.calls == []


def test_client_do_game_action_forwards_action_id_and_data_tuple():
    game_server, client, _writes = make_client()
    game = RecordingGame()
    game_server.game_id_to_game[7] = game
    client.game_id = 7

    client._on_message_do_game_action(3, "alpha", 4)

    assert game.calls == [("action", client.client_id, 3, ("alpha", 4))]


def test_client_do_game_action_ignores_client_outside_game():
    game_server, client, _writes = make_client()
    game = RecordingGame()
    game_server.game_id_to_game[7] = game

    client._on_message_do_game_action(3, "alpha", 4)

    assert game.calls == []


def test_client_game_chat_message_ignores_blank_or_client_outside_game():
    game_server, client, _writes = make_client()

    client._on_message_send_game_chat_message("hello")
    client.game_id = 7
    game_server.game_id_to_game[7] = GameWithClients({client.client_id})
    client._on_message_send_game_chat_message(" \n\t ")

    assert game_server.client_ids_and_messages == []


def test_client_create_game_validates_input_and_stores_created_game(monkeypatch):
    game_server, client, _writes = make_client()
    created_games = []

    class CreatedGame:
        def __init__(
            self,
            game_id,
            internal_game_id,
            mode,
            max_players,
            add_pending_messages,
        ):
            self.game_id = game_id
            self.internal_game_id = internal_game_id
            self.mode = mode
            self.max_players = max_players
            self.add_pending_messages = add_pending_messages
            self.joined_clients = []
            created_games.append(self)

        def join_game(self, joined_client):
            self.joined_clients.append(joined_client)
            joined_client.game_id = self.game_id

    monkeypatch.setattr(server, "Game", CreatedGame)

    client._on_message_create_game(GameModes.Singles.value, 3)

    assert len(created_games) == 1
    created_game = created_games[0]
    assert created_game.game_id == 1
    assert created_game.internal_game_id == 1
    assert created_game.mode == GameModes.Singles.value
    assert created_game.max_players == 3
    assert created_game.joined_clients == [client]
    assert game_server.game_id_to_game == {1: created_game}


@pytest.mark.parametrize(
    ("mode", "max_players"),
    [
        ("singles", 3),
        (GameModes.Max.value, 3),
        (GameModes.Singles.value, "3"),
        (GameModes.Singles.value, 0),
        (GameModes.Singles.value, 7),
    ],
)
def test_client_create_game_ignores_invalid_input(mode, max_players, monkeypatch):
    game_server, client, _writes = make_client()

    def fail_if_created(*_args):
        raise AssertionError("Game should not be created")

    monkeypatch.setattr(server, "Game", fail_if_created)

    client._on_message_create_game(mode, max_players)

    assert game_server.game_id_to_game == {}
