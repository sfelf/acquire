import base64
import hashlib
import os
import socket
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import pytest
import ujson
from enums import (
    CommandsToClient,
    CommandsToServer,
    GameActions,
    GameBoardTypes,
    GameModes,
    GameStates,
)

pytestmark = pytest.mark.e2e


class SockJSWebSocket:
    def __init__(self, base_url, timeout=60):
        parsed_url = urllib.parse.urlparse(base_url)
        self.host = parsed_url.hostname or "127.0.0.1"
        self.port = parsed_url.port or 80
        self.path = f"/sockjs/000/{uuid.uuid4().hex}/websocket"
        self.socket = None
        self.timeout = timeout
        self.read_buffer = b""

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._connect()
                return self
            except (TimeoutError, AssertionError, EOFError, OSError):
                if self.socket:
                    self.socket.close()
                    self.socket = None
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)

    def _connect(self):
        self.read_buffer = b""
        self.socket = socket.create_connection((self.host, self.port), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        response = self._read_http_response()
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        assert "101 Switching Protocols" in response
        assert f"sec-websocket-accept: {accept.lower()}" in response.lower()
        assert self.read_frame() == "o"

    def __exit__(self, exc_type, exc, traceback):
        if self.socket:
            self.socket.close()

    def _read_http_response(self):
        chunks = []
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.socket.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            data = b"".join(chunks)
        header_bytes, _, self.read_buffer = data.partition(b"\r\n\r\n")
        return header_bytes.decode("iso-8859-1")

    def _read_exactly(self, size, deadline=None):
        data = self.read_buffer[:size]
        self.read_buffer = self.read_buffer[size:]
        while len(data) < size:
            try:
                chunk = self.socket.recv(size - len(data))
            except TimeoutError:
                if deadline is not None and time.monotonic() < deadline:
                    continue
                self.read_buffer = data + self.read_buffer
                raise
            if not chunk:
                raise EOFError("websocket closed while reading")
            data += chunk
        return data

    def read_frame(self, deadline=None):
        header = self._read_exactly(2, deadline=deadline)
        opcode = header[0] & 0x0F
        payload_length = header[1] & 0x7F
        if payload_length == 126:
            payload_length = struct.unpack("!H", self._read_exactly(2, deadline=deadline))[0]
        elif payload_length == 127:
            payload_length = struct.unpack("!Q", self._read_exactly(8, deadline=deadline))[0]
        payload = self._read_exactly(payload_length, deadline=deadline)
        if opcode == 8:
            raise EOFError("websocket closed")
        assert opcode == 1
        return payload.decode("utf-8")

    def write_frame(self, text):
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        first_byte = 0x81
        if len(payload) < 126:
            header = struct.pack("!BB", first_byte, 0x80 | len(payload))
        elif len(payload) < 65536:
            header = struct.pack("!BBH", first_byte, 0x80 | 126, len(payload))
        else:
            header = struct.pack("!BBQ", first_byte, 0x80 | 127, len(payload))
        masked_payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.socket.sendall(header + mask + masked_payload)

    def send_message(self, message):
        self.write_frame(ujson.dumps([ujson.dumps(message)]))

    def read_messages(self, expected_command, timeout=10):
        return self.read_until(
            lambda message: message[0] == expected_command,
            timeout=timeout,
        )

    def read_until(self, message_matches, timeout=10):
        deadline = time.monotonic() + timeout
        messages = []
        self.socket.settimeout(1)
        while time.monotonic() < deadline:
            try:
                frame = self.read_frame(deadline=deadline)
            except TimeoutError:
                continue
            if frame == "h":
                continue
            assert frame[0] == "a"
            for item in ujson.loads(frame[1:]):
                decoded = ujson.loads(item)
                if decoded and isinstance(decoded[0], list):
                    messages.extend(decoded)
                else:
                    messages.append(decoded)
            if any(message_matches(message) for message in messages):
                return messages
        return messages


def _read_url(url_or_request, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(url_or_request, timeout=5) as response:
                return response.status, response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def test_python_gateway_serves_main_ui(e2e_base_url):
    status, body = _read_url(e2e_base_url.rstrip("/") + "/")

    assert status == 200
    assert "Acquire" in body
    assert 'id="page-login"' in body


def test_python_gateway_serves_main_ui_assets(e2e_base_url):
    css_status, css_body = _read_url(e2e_base_url.rstrip("/") + "/css/main.css")
    js_status, js_body = _read_url(e2e_base_url.rstrip("/") + "/js/main.js")

    assert css_status == 200
    assert "body" in css_body
    assert js_status == 200
    assert "SockJS" in js_body


def test_python_gateway_serves_stats_ui(e2e_base_url):
    status, body = _read_url(e2e_base_url.rstrip("/") + "/stats/")

    assert status == 200
    assert "Acquire stats" in body
    assert 'id="page-stats"' in body


def test_python_gateway_serves_stats_ui_assets(e2e_base_url):
    css_status, css_body = _read_url(e2e_base_url.rstrip("/") + "/stats/css/stats.css")
    js_status, js_body = _read_url(e2e_base_url.rstrip("/") + "/stats/js/stats.js")

    assert css_status == 200
    assert "body" in css_body
    assert js_status == 200
    assert "showRatings" in js_body


def test_python_gateway_accepts_report_error_posts(e2e_base_url):
    data = urllib.parse.urlencode(
        {
            "message": "e2e smoke",
            "trace": "client trace",
        }
    ).encode()
    request = urllib.request.Request(
        e2e_base_url.rstrip("/") + "/server/report-error",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    status, body = _read_url(request)

    assert status == 200
    assert body == ""


def test_python_gateway_supports_basic_game_workflow(e2e_base_url):
    username_1 = f"e2e-{uuid.uuid4().hex[:8]}"
    username_2 = f"e2e-{uuid.uuid4().hex[:8]}"

    with SockJSWebSocket(e2e_base_url) as client_1:
        client_1.send_message(["VERSION", username_1, ""])
        login_messages = client_1.read_messages(CommandsToClient.SetClientId.value)
        client_1_id = next(
            message[1]
            for message in login_messages
            if message[0] == CommandsToClient.SetClientId.value
        )
        assert [
            CommandsToClient.SetClientIdToData.value,
            client_1_id,
            username_1,
            None,
        ] in login_messages

        client_1.send_message([CommandsToServer.SendGlobalChatMessage.value, " hello from e2e "])
        assert [
            CommandsToClient.AddGlobalChatMessage.value,
            client_1_id,
            "hello from e2e",
        ] in client_1.read_messages(CommandsToClient.AddGlobalChatMessage.value)

        client_1.send_message([CommandsToServer.CreateGame.value, GameModes.Singles.value, 2])
        create_messages = client_1.read_messages(CommandsToClient.SetGameAction.value)
        created_game = next(
            message
            for message in create_messages
            if message[:1] == [CommandsToClient.SetGameState.value]
            and message[2:]
            == [
                GameStates.Starting.value,
                GameModes.Singles.value,
                2,
            ]
        )
        game_id = created_game[1]
        player_id_to_client = {
            message[2]: message[3]
            for message in create_messages
            if message[0] == CommandsToClient.SetGamePlayerJoin.value and message[1] == game_id
        }
        assert any(
            message[:3]
            == [
                CommandsToClient.SetGameAction.value,
                GameActions.StartGame.value,
                0,
            ]
            for message in create_messages
        )

        with SockJSWebSocket(e2e_base_url) as client_2:
            client_2.send_message(["VERSION", username_2, ""])
            second_login_messages = client_2.read_messages(CommandsToClient.SetClientId.value)
            client_2_id = next(
                message[1]
                for message in second_login_messages
                if message[0] == CommandsToClient.SetClientId.value
            )

            client_2.send_message([CommandsToServer.JoinGame.value, game_id])
            join_messages = client_2.read_messages(CommandsToClient.SetGamePlayerJoin.value)
            assert any(
                message[0] == CommandsToClient.SetGamePlayerJoin.value
                and message[1] == game_id
                and message[3] == client_2_id
                for message in join_messages
            )
            player_id_to_client.update(
                {
                    message[2]: message[3]
                    for message in join_messages
                    if message[0] == CommandsToClient.SetGamePlayerJoin.value
                    and message[1] == game_id
                }
            )
            assert 0 in player_id_to_client

            client_1.send_message(
                [CommandsToServer.SendGameChatMessage.value, " game chat from e2e "]
            )
            assert [
                CommandsToClient.AddGameChatMessage.value,
                client_1_id,
                "game chat from e2e",
            ] in client_1.read_messages(CommandsToClient.AddGameChatMessage.value)

            client_1.send_message(
                [CommandsToServer.DoGameAction.value, GameActions.StartGame.value]
            )
            client_2.send_message(
                [CommandsToServer.DoGameAction.value, GameActions.StartGame.value]
            )
            assert player_id_to_client[0] in {client_1_id, client_2_id}
            play_client = client_1 if player_id_to_client[0] == client_1_id else client_2
            other_client = client_2 if play_client is client_1 else client_1
            start_messages_1 = play_client.read_messages(CommandsToClient.SetTurn.value)
            start_messages_2 = other_client.read_messages(CommandsToClient.SetTurn.value)
            start_messages = start_messages_1 + start_messages_2
            assert [
                CommandsToClient.SetGameState.value,
                game_id,
                GameStates.InProgress.value,
            ] in start_messages
            assert [CommandsToClient.SetTurn.value, 0] in start_messages
            playable_tiles = [
                message
                for message in start_messages_1
                if message[0] == CommandsToClient.SetTile.value
                and message[4]
                in {
                    GameBoardTypes.Luxor.value,
                    GameBoardTypes.Tower.value,
                    GameBoardTypes.American.value,
                    GameBoardTypes.Festival.value,
                    GameBoardTypes.Worldwide.value,
                    GameBoardTypes.Continental.value,
                    GameBoardTypes.Imperial.value,
                    GameBoardTypes.WillPutLonelyTileDown.value,
                    GameBoardTypes.HaveNeighboringTileToo.value,
                    GameBoardTypes.WillFormNewChain.value,
                    GameBoardTypes.WillMergeChains.value,
                }
            ]
            assert playable_tiles
            tile_index = playable_tiles[0][1]

            play_client.send_message(
                [
                    CommandsToServer.DoGameAction.value,
                    GameActions.PlayTile.value,
                    tile_index,
                ]
            )
            played_tile = playable_tiles[0]
            if played_tile[4] == GameBoardTypes.WillFormNewChain.value:

                def expected_message(message):
                    return message[:2] == [
                        CommandsToClient.SetGameAction.value,
                        GameActions.SelectNewChain.value,
                    ]
            elif played_tile[4] == GameBoardTypes.WillMergeChains.value:

                def expected_message(message):
                    return message[:2] == [
                        CommandsToClient.SetGameAction.value,
                        GameActions.SelectMergerSurvivor.value,
                    ]
            else:

                def expected_message(message):
                    return message[:3] == [
                        CommandsToClient.SetGameBoardCell.value,
                        played_tile[2],
                        played_tile[3],
                    ]

            play_tile_messages = play_client.read_until(
                expected_message,
            )
            assert any(expected_message(message) for message in play_tile_messages)


def test_python_gateway_supports_watch_leave_and_rejoin_workflow(e2e_base_url):
    player_username = f"e2e-player-{uuid.uuid4().hex[:8]}"
    watcher_username = f"e2e-watch-{uuid.uuid4().hex[:8]}"

    with SockJSWebSocket(e2e_base_url) as player_client:
        player_client.send_message(["VERSION", player_username, ""])
        player_login_messages = player_client.read_messages(CommandsToClient.SetClientId.value)
        player_client_id = next(
            message[1]
            for message in player_login_messages
            if message[0] == CommandsToClient.SetClientId.value
        )

        player_client.send_message([CommandsToServer.CreateGame.value, GameModes.Singles.value, 2])
        create_messages = player_client.read_messages(CommandsToClient.SetGameAction.value)
        created_game = next(
            message
            for message in create_messages
            if message[:1] == [CommandsToClient.SetGameState.value]
            and message[2:]
            == [
                GameStates.Starting.value,
                GameModes.Singles.value,
                2,
            ]
        )
        game_id = created_game[1]
        player_id = next(
            message[2]
            for message in create_messages
            if message[:2] == [CommandsToClient.SetGamePlayerJoin.value, game_id]
            and message[3] == player_client_id
        )

        with SockJSWebSocket(e2e_base_url) as watcher_client:
            watcher_client.send_message(["VERSION", watcher_username, ""])
            watcher_login_messages = watcher_client.read_messages(
                CommandsToClient.SetClientId.value
            )
            watcher_client_id = next(
                message[1]
                for message in watcher_login_messages
                if message[0] == CommandsToClient.SetClientId.value
            )
            assert any(
                message[:3]
                == [
                    CommandsToClient.SetGameState.value,
                    game_id,
                    GameStates.Starting.value,
                ]
                for message in watcher_login_messages
            )

            watcher_client.send_message([CommandsToServer.WatchGame.value, game_id])
            watch_messages = watcher_client.read_messages(
                CommandsToClient.SetGameWatcherClientId.value
            )
            assert [
                CommandsToClient.SetGameWatcherClientId.value,
                game_id,
                watcher_client_id,
            ] in watch_messages

            watcher_client.send_message([CommandsToServer.LeaveGame.value])
            assert [
                CommandsToClient.ReturnWatcherToLobby.value,
                game_id,
                watcher_client_id,
            ] in watcher_client.read_messages(CommandsToClient.ReturnWatcherToLobby.value)

        player_client.send_message([CommandsToServer.LeaveGame.value])
        assert [
            CommandsToClient.SetGamePlayerLeave.value,
            game_id,
            player_id,
            player_client_id,
        ] in player_client.read_messages(CommandsToClient.SetGamePlayerLeave.value)

        player_client.send_message([CommandsToServer.RejoinGame.value, game_id])
        rejoin_messages = player_client.read_messages(CommandsToClient.SetGamePlayerRejoin.value)
        assert [
            CommandsToClient.SetGamePlayerRejoin.value,
            game_id,
            player_id,
            player_client_id,
        ] in rejoin_messages
