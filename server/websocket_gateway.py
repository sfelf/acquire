"""Bridge FastAPI websocket connections to the in-process game server.

The legacy Node gateway translated SockJS client frames into the Python
server's newline-delimited socket protocol. This module keeps that translation
boundary explicit while the runtime is consolidated into Python: FastAPI owns
the browser websocket, and the existing `server.Server` / `server.Client`
classes still own authoritative game state and command handling.
"""

from __future__ import annotations

import asyncio
import dataclasses

import ujson
from fastapi import WebSocket

import server as game_server_module

SOCKJS_OPEN_FRAME = "o"
SOCKJS_HEARTBEAT_FRAME = "h"


@dataclasses.dataclass
class GatewayConnection:
    """Track one browser websocket connection and its server-side client."""

    socket_id: str
    websocket: WebSocket
    outbound_frames: asyncio.Queue[str | None] = dataclasses.field(
        default_factory=asyncio.Queue
    )
    client_id: int | None = None
    client: game_server_module.Client | None = None


def encode_sockjs_messages(messages_json: str) -> str:
    """Wrap a legacy client-message JSON string in a SockJS websocket frame.

    Args:
        messages_json: JSON string that should be delivered as one SockJS
            application message.

    Returns:
        SockJS array frame text suitable for a raw websocket transport.
    """
    return "a" + ujson.dumps([messages_json])


def decode_sockjs_frame(frame: str) -> list[str]:
    """Decode one inbound SockJS websocket frame into application messages.

    The browser SockJS client sends a JSON array of string application payloads
    over the raw websocket transport. The old Node gateway received those
    unwrapped strings from the `sockjs` package; the Python gateway performs
    that unwrapping directly.

    Args:
        frame: Raw websocket text frame.

    Returns:
        Application message strings contained in the frame.

    Raises:
        ValueError: If the frame is not a SockJS application message array.
    """
    if frame == SOCKJS_HEARTBEAT_FRAME:
        return []

    try:
        parsed = ujson.loads(frame)
    except ValueError as exc:
        raise ValueError("invalid SockJS frame JSON") from exc

    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("SockJS frame must be a list of strings")
    return parsed


def normalize_client_payload(payload: str) -> str:
    r"""Normalize a client payload the same way the Node gateway did.

    The legacy gateway called `data.replace(/\s+/g, " ")` before forwarding
    non-login client messages to Python. That behavior is observable for chat
    and malformed JSON payloads, so the Python gateway keeps it until the client
    protocol is intentionally changed.

    Args:
        payload: Client application payload string.

    Returns:
        Whitespace-normalized payload.
    """
    return " ".join(payload.split())


class SockJSGateway:
    """Translate SockJS websocket traffic into existing game server calls.

    The gateway owns only connection bookkeeping and wire-format adaptation.
    Game state remains in `server.Server`, and client commands still flow
    through `server.Client.on_message` so this migration does not fork gameplay
    behavior from the already-covered Python server.
    """

    def __init__(self, game_server: game_server_module.Server | None = None) -> None:
        """Initialize the gateway around a Python game server.

        Args:
            game_server: Existing server instance to expose. A new empty server
                is created when omitted.
        """
        self.game_server = game_server or game_server_module.Server()
        self.game_server.transport_write = self.write_from_game_server
        self.socket_id_to_connection: dict[str, GatewayConnection] = {}
        self.client_id_to_connection: dict[int, GatewayConnection] = {}
        self.lock = asyncio.Lock()

    def new_connection(self, socket_id: str, websocket: WebSocket) -> GatewayConnection:
        """Create gateway bookkeeping for an accepted websocket.

        Args:
            socket_id: SockJS session id from the websocket URL.
            websocket: Accepted FastAPI websocket.

        Returns:
            Connection state for the websocket.
        """
        connection = GatewayConnection(socket_id=socket_id, websocket=websocket)
        self.socket_id_to_connection[socket_id] = connection
        return connection

    def remove_connection(self, connection: GatewayConnection) -> None:
        """Remove gateway bookkeeping for a websocket connection.

        Args:
            connection: Connection state to remove from lookup tables.
        """
        self.socket_id_to_connection.pop(connection.socket_id, None)
        if connection.client_id is not None:
            self.client_id_to_connection.pop(connection.client_id, None)

    def login(
        self,
        connection: GatewayConnection,
        *,
        username: str,
        ip_address: str | None,
        replace_existing_user: bool,
    ) -> None:
        """Create the server-side client for an authenticated connection.

        This calls the existing `server.Client` constructor, which allocates
        the client id, emits initial state, and may disconnect another client
        when password-authenticated login replaces an existing username.

        Args:
            connection: Authenticated websocket connection.
            username: Normalized username from the auth layer.
            ip_address: Client IP address reported by the incoming request.
            replace_existing_user: Whether this login should replace an
                existing connection with the same username.
        """
        connection.client = game_server_module.Client(
            self.game_server,
            username,
            ip_address,
            connection.socket_id,
            replace_existing_user,
        )

    def disconnect(self, connection: GatewayConnection) -> None:
        """Disconnect a mapped server client and remove gateway state.

        Args:
            connection: Websocket connection being closed.
        """
        if (
            connection.client is not None
            and connection.client_id in self.game_server.client_id_to_client
        ):
            connection.client.disconnect()
        self.remove_connection(connection)

    def receive_client_payload(self, connection: GatewayConnection, payload: str) -> None:
        """Forward one authenticated client payload to the game server.

        Args:
            connection: Authenticated websocket connection.
            payload: Application payload string from the client.
        """
        if connection.client is None:
            return
        connection.client.on_message(normalize_client_payload(payload).encode())

    def write_from_game_server(self, data: bytes) -> None:
        """Handle newline-delimited writes emitted by `server.Server`.

        The existing Python server still writes the same control/data lines it
        used to send to Node. This method consumes those lines in-process:
        connect lines populate lookup tables, disconnect lines close browser
        sockets, and data lines are queued as SockJS frames for mapped clients.

        Args:
            data: One or more newline-delimited gateway protocol lines.
        """
        for line in data.decode().splitlines():
            if not line:
                continue
            key, value = line.split(" ", 1)
            if key == "connect":
                self._handle_connect(value)
            elif key == "disconnect":
                self._handle_disconnect(value)
            else:
                self._handle_messages(key, value)

    def _handle_connect(self, value: str) -> None:
        socket_id, client_id = ujson.loads(value)
        connection = self.socket_id_to_connection.get(socket_id)
        if connection is None:
            return
        connection.client_id = client_id
        self.client_id_to_connection[client_id] = connection

    def _handle_disconnect(self, value: str) -> None:
        connection = self.client_id_to_connection.get(int(value))
        if connection is None:
            return
        connection.outbound_frames.put_nowait(None)

    def _handle_messages(self, key: str, value: str) -> None:
        frame = encode_sockjs_messages(value)
        for client_id_text in key.split(","):
            connection = self.client_id_to_connection.get(int(client_id_text))
            if connection is None:
                continue
            connection.outbound_frames.put_nowait(frame)
