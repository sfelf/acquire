# Architecture Notes

Acquire currently runs as a split Node.js and Python application.

## Runtime Components

- The Node.js server in `server/server.js` owns HTTP endpoints, SockJS connections, client login handling, static gateway behavior, and user database checks.
- The Python server in `server/server.py` owns game state and the gameplay protocol.
- The Node.js process communicates with the Python process through Unix sockets.
- MySQL is the backing database.
- Client assets are built from files under `client/` using the legacy shell scripts.

## Modernization Direction

The long-term direction is to remove the Node.js runtime and keep the backend in Python. That replacement should happen only after the current behavior is protected by pytest tests, protocol tests, and historical-log golden replay tests.

## Current Risk Areas

- Database credentials and socket paths are hard-coded.
- Deployment depends on shell scripts and host-specific assumptions.
- The Node.js gateway owns behavior that must be captured before deprecation.
- Runtime dependencies are intentionally old and should not be broadly upgraded until regression coverage exists.
