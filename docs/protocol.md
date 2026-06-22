# Protocol Notes

The browser client now connects to the Python FastAPI gateway. The historical
line-oriented gateway protocol remains documented because `server/server.py`
still exposes the parser and `server/websocket_gateway.py` consumes the
game-server outbound line format in process.

## Historical Gateway To Python

- `connect <json>` creates a Python client for a SockJS connection.
- `disconnect <client_id>` disconnects a Python client.
- `<client_id> <json>` forwards a client message to the Python game server.

## Python To Gateway

- `connect <json>` maps a SockJS socket id to a Python client id.
- `disconnect <client_id>` asks the gateway to close a client socket.
- `<client_ids> <json>` sends messages to one or more connected clients.

## Modernization Notes

The protocol should stay covered by tests before it is changed. The Python
backend preserves the existing client-facing behavior where practical.

Parser-level, individual-game, redacted real-server, and replay-summary golden fixtures live under `tests/fixtures/game_logs/` and document how current server logs are interpreted.
