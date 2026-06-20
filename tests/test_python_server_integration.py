import asyncio

import pytest
import server
import ujson
from enums import CommandsToClient, CommandsToServer


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
            pytest.skip("local socket binding is not permitted: %s" % exc)
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
                    + ujson.dumps(
                        [CommandsToServer.SendGlobalChatMessage.value, " hello "]
                    )
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
