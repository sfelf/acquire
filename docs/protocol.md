# Protocol Notes

The current client, Node.js gateway, and Python game server communicate through a line-oriented protocol.

## Node.js To Python

- `connect <json>` creates a Python client for a SockJS connection.
- `disconnect <client_id>` disconnects a Python client.
- `<client_id> <json>` forwards a client message to the Python game server.

## Python To Node.js

- `connect <json>` maps a SockJS socket id to a Python client id.
- `disconnect <client_id>` asks Node.js to close a client socket.
- `<client_ids> <json>` sends messages to one or more connected clients.

## Modernization Notes

The protocol should be covered by tests before it is changed. The first Python-only backend should preserve the existing client-facing behavior where practical.

Parser-level and individual-game golden fixtures live under `tests/fixtures/game_logs/` and document how current server logs are interpreted.
