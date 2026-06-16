import ujson
import pytest
import server
from enums import CommandsToClient, CommandsToServer, Errors


pytestmark = pytest.mark.unit


class ExpiringGame:
    def __init__(self, game_id, internal_game_id, expiration_time):
        self.game_id = game_id
        self.internal_game_id = internal_game_id
        self.expiration_time = expiration_time


class GameWithClients:
    def __init__(self, client_ids):
        self.client_ids = client_ids


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
        b'10,20 [[23,1]]\n',
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
        (
            b"2 [[0,"
            + str(Errors.UsernameAlreadyInUse.value).encode()
            + b"]]\n"
        ),
        b"disconnect 2\n",
    ]
