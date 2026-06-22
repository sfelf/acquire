# Architecture Notes

Acquire currently runs as a Python application with a legacy Node.js compatibility gateway.

## Runtime Components

- The FastAPI app in `server/http_server.py` owns the default local browser gateway, SockJS-compatible connections, Python-migrated HTTP routes, and static asset serving.
- The Python server in `server/server.py` owns game state and the gameplay protocol.
- The Node.js server in `server/server.js` remains available as a legacy browser gateway behind the `legacy-node` Docker Compose profile.
- The legacy Node.js process communicates with the socket-based Python process through Unix sockets.
- MySQL is the backing database.
- Client assets are built from files under `client/` using the legacy shell scripts.

## Modernization Direction

The long-term direction is to remove the Node.js runtime and keep the backend in Python. That replacement should happen only after the current behavior is protected by pytest tests, protocol tests, and historical-log golden replay tests.

## Current Risk Areas

- Database credentials and socket paths are hard-coded.
- Deployment depends on shell scripts and host-specific assumptions.
- The legacy Node.js gateway still owns compatibility behavior that must stay available until the Python path has enough soak time.
- Runtime dependencies are intentionally old and should not be broadly upgraded until regression coverage exists.

## Phase 5 Runtime Boundary Inventory

Phase 5 consolidates the backend into Python while preserving the current browser
protocol until tests prove it is safe to change. The historical runtime boundary
is the legacy Node.js gateway in `server/server.js`: it serves HTTP traffic,
owns SockJS connection setup, performs user/password database checks, and
forwards validated realtime messages to `server/server.py` over `python.sock`.
The default local path now routes browser and e2e traffic through the FastAPI
gateway while keeping that Node path available for compatibility checks.

### HTTP And Static Routes

| Route or listener | Current owner | Current behavior | Python migration target | Coverage |
| --- | --- | --- | --- | --- |
| `GET /` and generated `client/main` assets | FastAPI app by default; Node only in the legacy profile | Serves the generated `client/main` tree, including `index.html`, `/css/main.css`, `/js/main.js`, supporting JavaScript modules, source maps, and `/static/*` media. | Keep FastAPI as the Python local runtime static route. | `tests/test_python_http_server.py` covers the FastAPI route; Docker-backed e2e now covers the Python gateway default. |
| `GET /stats/` and generated `client/stats` assets | FastAPI app by default; Node only in the legacy profile | Serves the generated `client/stats` tree, including `index.html`, `/stats/css/stats.css`, and `/stats/js/stats.js`. | Keep FastAPI as the Python local runtime stats route. | `tests/test_python_http_server.py` covers the FastAPI route; Docker-backed e2e now covers the Python gateway default. |
| `POST /server/report-error` | FastAPI app by default; Node only in the legacy profile | Accepts form-encoded `message` and `trace`, validates the request size, normalizes embedded newlines for logging, writes request headers to stdout, and returns an empty `200` response. | Keep this route in FastAPI. | `tests/test_python_http_server.py` covers FastAPI behavior; `tests/test_local_ui_e2e.py::test_python_gateway_accepts_report_error_posts` covers the default gateway. |
| `POST /server/set-password` | FastAPI app by default; Node only in the legacy profile | Form-decodes `version`, `username`, and `password` with Pydantic payload models, then delegates legacy normalization and error-code decisions to Python auth. Malformed, uppercase, or non-64-character password hashes return `Errors.GenericError`, not a password-specific validation error. The response has a JSON content type and a stringified error id or `null`. | Keep password setup and user persistence in Python. | `tests/test_auth.py`, `tests/test_mysql_integration.py`, and `tests/test_python_http_server.py` cover success, whitespace normalization, existing password, invalid username, invalid password hash returning `Errors.GenericError`, version mismatch, database error behavior, and real ORM persistence. |
| `JAVASCRIPT_PORT` or `javascript.sock` | Node gateway | Listens on `0.0.0.0:$JAVASCRIPT_PORT` when configured; otherwise listens on `javascript.sock`. Docker exposes this as the local browser UI during compatibility testing. | Replace with the Python gateway listener, then keep the Node listener only behind an explicit compatibility profile until removal. | Docker-backed e2e tests exercise the port-based listener. |

### SockJS Gateway Responsibilities

| Boundary | Current owner | Current behavior | Python migration target | Coverage |
| --- | --- | --- | --- | --- |
| `/sockjs` protocol endpoints, including `GET /sockjs/info` | FastAPI app by default; Node only in the legacy profile | Supports SockJS negotiation for the generated browser client before opening a session websocket. | Keep Python support for the current SockJS negotiation surface until the browser transport changes deliberately. | `tests/test_python_http_server.py` covers negotiation; Docker-backed e2e covers the default Python gateway. |
| `GET /sockjs/.../websocket` | FastAPI app by default; Node only in the legacy profile | Accepts SockJS websocket and websocket-raw transports at `/sockjs`. | Keep the Python websocket path speaking the existing client framing. | `tests/test_local_ui_e2e.py` opens websocket connections through the SockJS path. |
| First client data frame | Node gateway | Treats the first frame as login JSON: `[version, username, password]`. Whitespace is collapsed in all three fields before validation. Malformed JSON or non-string fields that fail normalization close the socket without sending `FatalError`. The forwarded `ip_address` is only `socket.headers["x-real-ip"]`; the SockJS login path does not fall back to the TCP remote address, so local clients without that header currently appear as `null` in later `SetClientIdToData` messages. | Preserve this login contract, malformed-frame close behavior, and IP-address behavior in Python until the client protocol or privacy policy changes deliberately. | Existing e2e workflows cover successful passwordless login only. |
| Version validation | Node gateway | Rejects login when the normalized client version differs from `server_version` with `Errors.NotUsingLatestVersion`, sends `CommandsToClient.FatalError`, then closes the socket. Local development uses the literal `VERSION`; distribution builds replace `data-version=VERSION` in the built client and `server_version = 'VERSION'` in generated `dist/server.js` with a hash of the built index. | Move validation into Python auth/session handling while preserving the build-injected cache-busting version token. | Needs Phase 5 PR 3 coverage for local `VERSION` and generated distribution version behavior. |
| Username validation | Node gateway | Requires 1 to 32 printable ASCII characters; otherwise sends `Errors.InvalidUsername` as a fatal error and closes the socket. | Move validation into Python auth/session handling. | Needs Phase 5 PR 3 coverage. |
| Password lookup | Node gateway | Looks up `user.name` in MySQL and enforces password branches before connecting to Python. No row plus an empty password is allowed without creating a user record; no row plus a non-empty password returns `Errors.ProvidedPassword`. A passwordless existing user allows only an empty password; any non-empty password returns `Errors.ProvidedPassword`. A password-protected user requires a non-empty exact password match; an empty password returns `Errors.MissingPassword`, and any non-empty non-matching string returns `Errors.IncorrectPassword`. Login does not validate password hash format. If the query fails, Node sends `FatalError(GenericError)`, closes the socket, and does not create a Python session. | Move database lookup and password enforcement into Python. | Needs Phase 5 PR 3 coverage, including no-row login semantics, malformed login password strings, and database-error behavior. |
| Existing username replacement | Split boundary | Node passes `replace_existing_user=true` to Python only for successful password-authenticated users; Python disconnects the previous connected client for that username. Passwordless duplicate usernames are rejected by Python with `Errors.UsernameAlreadyInUse`. | Keep the replacement and duplicate-login behavior intact when auth moves to Python. | Python duplicate-user behavior has unit/integration coverage; authenticated replacement needs Phase 5 PR 3 coverage. |
| Later client data frames | FastAPI app by default; Node only in the legacy profile | Dispatches mapped client payloads to `Client.on_message` and preserves legacy whitespace normalization. Frames received after the login frame but before mapping are silently dropped rather than queued or dispatched. | Keep direct Python dispatch until protocol changes are intentional. | `tests/test_python_server_integration.py`, `tests/test_python_http_server.py`, and e2e workflow tests cover representative gameplay commands and pre-mapping drops. |
| Browser socket close | FastAPI app by default; Node only in the legacy profile | Removes gateway mappings and calls the same Python client disconnect behavior when a mapped websocket closes. | Keep direct Python disconnect behavior without the intermediate Node socket protocol. | Integration and e2e tests cover disconnect, leave, watch, and rejoin flows. |

### Node To Python Socket Protocol

The gateway currently connects to `python.sock` and sends newline-delimited
records. Python responds with newline-delimited records back to Node.

| Direction | Record shape | Current behavior | Migration note |
| --- | --- | --- | --- |
| Node to Python | `connect [username, ip_address, socket_id, replace_existing_user]\n` | Creates a Python `Client`, allocates a client id, emits the gateway connect mapping, and sends initial lobby/game state. | This is the main boundary to remove once Python owns login and websocket connections. |
| Node to Python | `disconnect <client_id>\n` | Disconnects the Python client if it still exists. | Direct Python gateway code should call `Client.disconnect()` or an equivalent server method. |
| Node to Python | `<client_id> <command-json>\n` | Dispatches `CommandsToServer` payloads to the connected Python client. | Direct Python gateway code should reuse this command dispatch path or keep a small compatibility adapter. |
| Python to Node | `connect [socket_id, client_id]\n` | Teaches Node which browser socket maps to the allocated Python client id. | Not needed once Python owns websocket sessions. |
| Python to Node | `disconnect <client_id>\n` | Tells Node to close the browser socket for a disconnected client. | Python gateway should close the websocket directly. |
| Python to Node | `<client-id-list> <command-json>\n` | Sends one command batch to one or more browser sockets. | Python gateway should serialize the same client command payloads to connected websockets. |

### Gameplay Commands Already Owned By Python

After login, gameplay commands are already handled by `server/server.py`:

- `CreateGame`
- `JoinGame`
- `RejoinGame`
- `WatchGame`
- `LeaveGame`
- `DoGameAction`
- `SendGlobalChatMessage`
- `SendGameChatMessage`

These commands are covered by Python integration tests and Docker-backed e2e
tests for representative lobby, chat, game creation, joining, starting, tile
play, watching, leaving, disconnecting, and rejoining workflows.

### Phase 5 Migration Checklist

1. Add missing characterization coverage for Node-owned auth and
   `/server/set-password` behavior before moving it, including whitespace
   normalization, no-row login semantics, login password-format handling,
   malformed login close behavior, build-injected version tokens,
   invalid set-password hash errors, database-error handling, and the SockJS
   `x-real-ip` behavior.
2. Move `/server/report-error` and static asset serving into FastAPI or an
   explicitly documented Python-adjacent local asset service, including
   generated JavaScript, CSS, source maps, and media files.
3. Move password setup, login validation, user lookup, and duplicate-session
   policy into Python with MySQL-backed tests.
4. Keep Python-owned HTTP routes in FastAPI with Pydantic request models while
   preserving legacy response bodies and error codes.
5. Add a Python websocket or SockJS-compatible path that preserves the full
   browser negotiation surface, current client framing, pre-mapping frame-drop
   behavior, and command payloads.
6. Run e2e workflows against the Python gateway by default while keeping the
   legacy Node gateway available for targeted compatibility checks.
7. Make the Python gateway the local-development and e2e default.
8. Remove the Node gateway from the main runtime only after the Python path owns
   HTTP, auth, websocket, and client command delivery.
