import asyncio

import pytest
import ujson

import server
from acquire.enums import CommandsToClient, CommandsToServer, GameActions, GameModes, GameStates

pytestmark = pytest.mark.integration


class FakeTransport:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)


def _decode_transport_writes(transport):
    lines = b"".join(transport.writes).decode().splitlines()
    messages = []
    for line in lines:
        recipient, payload = line.split(" ", 1)
        messages.append((recipient, ujson.decode(payload)))
    return messages


def _decode_transport_writes_since(transport, start_index):
    lines = b"".join(transport.writes[start_index:]).decode().splitlines()
    messages = []
    for line in lines:
        recipient, payload = line.split(" ", 1)
        messages.append((recipient, ujson.decode(payload)))
    return messages


def _flatten_client_messages(decoded_writes):
    messages = []
    for recipient, payload in decoded_writes:
        if recipient in {"connect", "disconnect"}:
            continue
        if payload and isinstance(payload[0], list):
            messages.extend(payload)
        else:
            messages.append(payload)
    return messages


def _send_protocol_line(protocol, client_id, message):
    protocol.data_received(f"{client_id} {ujson.dumps(message)}\n".encode())


def _connect_protocol_client(protocol, username, socket_id=None):
    socket_id = socket_id or f"socket-{username}"
    protocol.data_received((f'connect ["{username}","127.0.0.1","{socket_id}",false]\n').encode())


def _messages_after(transport, start_index):
    return _flatten_client_messages(_decode_transport_writes_since(transport, start_index))


async def _read_protocol_messages(reader, expected_command, timeout=1):
    deadline = asyncio.get_running_loop().time() + timeout
    messages = []
    while asyncio.get_running_loop().time() < deadline:
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not line:
            break
        recipient, payload = line.decode().strip().split(" ", 1)
        if recipient in {"connect", "disconnect"}:
            continue
        decoded_messages = ujson.decode(payload)
        if decoded_messages and isinstance(decoded_messages[0], list):
            messages.extend(decoded_messages)
        else:
            messages.append(decoded_messages)
        if any(message[0] == expected_command for message in messages):
            return messages
    return messages


def test_protocol_reader_ignores_control_lines_and_preserves_messages():
    class FakeReader:
        def __init__(self):
            self.lines = [
                b'connect ["socket-1",1]\n',
                b"1 [[1,1]]\n",
            ]

        async def readline(self):
            return self.lines.pop(0) if self.lines else b""

    messages = asyncio.run(
        _read_protocol_messages(FakeReader(), CommandsToClient.SetClientId.value)
    )

    assert messages == [[CommandsToClient.SetClientId.value, 1]]


def test_server_protocol_accepts_fragmented_connect_messages():
    game_server = server.Server()
    server_protocol = server.ServerProtocol(game_server)
    transport = FakeTransport()
    server_protocol.connection_made(transport)

    server_protocol.data_received(b'connect ["alice","127.0.')
    server_protocol.data_received(b'0.1","socket-1",false]\n')

    assert game_server.client_ids == {1}
    assert game_server.username_to_client["alice"].client_id == 1
    assert _decode_transport_writes(transport)[0] == ("connect", ["socket-1", 1])


def test_server_protocol_disconnect_removes_connected_client():
    game_server = server.Server()
    server_protocol = server.ServerProtocol(game_server)
    transport = FakeTransport()
    server_protocol.connection_made(transport)
    server_protocol.data_received(b'connect ["alice","127.0.0.1","socket-1",false]\n')

    server_protocol.data_received(b"disconnect 1\n")

    assert game_server.client_ids == set()
    assert game_server.client_id_to_client == {}
    assert game_server.username_to_client == {}
    assert _decode_transport_writes(transport)[-1] == ("disconnect", 1)


def test_python_server_protocol_handles_connect_and_global_chat():
    async def run_protocol_smoke():
        game_server = server.Server()
        server_protocol = server.ServerProtocol(game_server)
        try:
            tcp_server = await asyncio.get_running_loop().create_server(
                lambda: server_protocol,
                "127.0.0.1",
                0,
            )
        except PermissionError as exc:
            pytest.skip(f"local socket binding is not permitted: {exc}")
        host, port = tcp_server.sockets[0].getsockname()
        writer = None
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.write(b'connect ["alice","127.0.0.1","socket-1",false]\n')
            await writer.drain()

            connect_messages = await _read_protocol_messages(
                reader,
                CommandsToClient.SetClientId.value,
            )
            assert [CommandsToClient.SetClientId.value, 1] in connect_messages
            assert game_server.client_ids == {1}
            assert game_server.username_to_client["alice"].client_id == 1

            writer.write(
                (
                    "1 "
                    + ujson.dumps([CommandsToServer.SendGlobalChatMessage.value, " hello "])
                    + "\n"
                ).encode()
            )
            await writer.drain()

            chat_messages = await _read_protocol_messages(
                reader,
                CommandsToClient.AddGlobalChatMessage.value,
            )
            assert [
                CommandsToClient.AddGlobalChatMessage.value,
                1,
                "hello",
            ] in chat_messages
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
            tcp_server.close()
            await tcp_server.wait_closed()

    asyncio.run(run_protocol_smoke())


def test_protocol_handles_create_join_start_and_game_chat_flow():
    game_server = server.Server()
    server_protocol = server.ServerProtocol(game_server)
    transport = FakeTransport()
    server_protocol.connection_made(transport)

    _connect_protocol_client(server_protocol, "alice", "socket-alice")
    alice_id = game_server.username_to_client["alice"].client_id
    write_index = len(transport.writes)

    _send_protocol_line(
        server_protocol,
        alice_id,
        [CommandsToServer.CreateGame.value, GameModes.Singles.value, 2],
    )
    create_messages = _messages_after(transport, write_index)
    game_id = next(
        message[1]
        for message in create_messages
        if message[:3]
        == [
            CommandsToClient.SetGameState.value,
            1,
            GameStates.Starting.value,
        ]
    )
    assert game_id == 1
    assert [
        CommandsToClient.SetGamePlayerJoin.value,
        game_id,
        0,
        alice_id,
    ] in create_messages
    assert [CommandsToClient.SetGameAction.value, GameActions.StartGame.value] in [
        message[:2] for message in create_messages
    ]

    _connect_protocol_client(server_protocol, "bob", "socket-bob")
    bob_id = game_server.username_to_client["bob"].client_id
    write_index = len(transport.writes)

    _send_protocol_line(
        server_protocol,
        bob_id,
        [CommandsToServer.JoinGame.value, game_id],
    )
    join_messages = _messages_after(transport, write_index)
    bob_player_id = next(
        message[2]
        for message in join_messages
        if message[:2] == [CommandsToClient.SetGamePlayerJoin.value, game_id]
        and message[3] == bob_id
    )
    assert bob_player_id in {0, 1}
    assert [
        CommandsToClient.SetGameState.value,
        game_id,
        GameStates.StartingFull.value,
    ] in join_messages

    write_index = len(transport.writes)
    _send_protocol_line(
        server_protocol,
        alice_id,
        [CommandsToServer.SendGameChatMessage.value, " hello game "],
    )
    game_chat_messages = _decode_transport_writes_since(transport, write_index)
    assert game_chat_messages == [
        (
            "1,2",
            [[CommandsToClient.AddGameChatMessage.value, alice_id, "hello game"]],
        )
    ]

    _send_protocol_line(
        server_protocol,
        alice_id,
        [CommandsToServer.DoGameAction.value, GameActions.StartGame.value],
    )
    _send_protocol_line(
        server_protocol,
        bob_id,
        [CommandsToServer.DoGameAction.value, GameActions.StartGame.value],
    )

    assert game_server.game_id_to_game[game_id].state == GameStates.InProgress.value
    assert any(
        message == [CommandsToClient.SetTurn.value, 0] for message in _messages_after(transport, 0)
    )


def test_protocol_handles_watch_leave_disconnect_and_rejoin_flow():
    game_server = server.Server()
    server_protocol = server.ServerProtocol(game_server)
    transport = FakeTransport()
    server_protocol.connection_made(transport)

    _connect_protocol_client(server_protocol, "alice", "socket-alice-1")
    alice_id = game_server.username_to_client["alice"].client_id
    _send_protocol_line(
        server_protocol,
        alice_id,
        [CommandsToServer.CreateGame.value, GameModes.Singles.value, 2],
    )
    game_id = 1

    _connect_protocol_client(server_protocol, "watcher", "socket-watcher")
    watcher_id = game_server.username_to_client["watcher"].client_id
    write_index = len(transport.writes)
    _send_protocol_line(
        server_protocol,
        watcher_id,
        [CommandsToServer.WatchGame.value, game_id],
    )
    watch_messages = _messages_after(transport, write_index)
    assert [
        CommandsToClient.SetGameWatcherClientId.value,
        game_id,
        watcher_id,
    ] in watch_messages
    assert game_server.client_id_to_client[watcher_id].game_id == game_id
    assert watcher_id in game_server.game_id_to_game[game_id].watcher_client_ids

    write_index = len(transport.writes)
    _send_protocol_line(
        server_protocol,
        watcher_id,
        [CommandsToServer.LeaveGame.value],
    )
    leave_messages = _messages_after(transport, write_index)
    assert [
        CommandsToClient.ReturnWatcherToLobby.value,
        game_id,
        watcher_id,
    ] in leave_messages
    assert game_server.client_id_to_client[watcher_id].game_id is None

    write_index = len(transport.writes)
    server_protocol.data_received(f"disconnect {alice_id}\n".encode())
    disconnect_messages = _messages_after(transport, write_index)
    assert [
        CommandsToClient.SetGamePlayerLeave.value,
        game_id,
        0,
        alice_id,
    ] in disconnect_messages
    assert alice_id not in game_server.client_id_to_client
    assert "alice" not in game_server.username_to_client

    _connect_protocol_client(server_protocol, "alice", "socket-alice-2")
    reconnected_alice_id = game_server.username_to_client["alice"].client_id
    write_index = len(transport.writes)
    _send_protocol_line(
        server_protocol,
        reconnected_alice_id,
        [CommandsToServer.RejoinGame.value, game_id],
    )
    rejoin_messages = _messages_after(transport, write_index)
    assert [
        CommandsToClient.SetGamePlayerRejoin.value,
        game_id,
        0,
        reconnected_alice_id,
    ] in rejoin_messages
    assert game_server.client_id_to_client[reconnected_alice_id].game_id == game_id
