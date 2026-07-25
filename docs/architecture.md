# Architecture Notes

Acquire currently runs as a Python backend with npm-based client asset build
tooling.

## Runtime Components

- The FastAPI app in `acquire.http_server` owns the default local browser
  gateway, Python-migrated HTTP routes, and static asset serving.
- `acquire.realtime` owns SockJS-compatible WebSocket adaptation.
- `acquire.game_server` owns game state and the gameplay protocol.
- `acquire.log_tools` owns historical parsing, replay, and manual reports;
  `acquire.recreate_game` restores serialized in-progress games; and
  `acquire.stats` owns database log ingestion, ratings, and published stats.
- Files with the former names under `server/` are temporary compatibility
  wrappers for existing direct-file commands.
- Postgres is the application runtime database. MySQL support is limited to the
  optional backup-import tools under `acquire.migration`; loading that package
  does not initialize the application ORM or runtime database engine.
- Client assets are built from files under `client/` using npm scripts or the
  opt-in `client-build` Docker Compose profile. Generated asset files remain
  gitignored build outputs; see `docs/client-assets.md`.

## Modernization Direction

The backend runtime is now Python-owned. The remaining Node.js usage is limited
to frontend asset generation through the npm client build scripts.

## Current Risk Areas

- Deployment depends on shell scripts and host-specific assumptions.
- Runtime dependencies are intentionally old and should not be broadly upgraded until regression coverage exists.

## Phase 5 Runtime Boundary Inventory

Phase 5 consolidated the backend into Python while preserving the current
browser protocol. The historical runtime boundary was the removed legacy
Node.js gateway in `server/server.js`: it served HTTP traffic, owned SockJS
connection setup, performed user/password database checks, and forwarded
validated realtime messages to `server/server.py` over `python.sock`. The local
path now routes browser and e2e traffic through the FastAPI gateway.

### HTTP And Static Routes

| Route or listener | Current owner | Current behavior | Python migration target | Coverage |
| --- | --- | --- | --- | --- |
| `GET /` and generated `client/main` assets | FastAPI app | Serves the generated `client/main` tree, including `index.html`, `/css/main.css`, `/js/main.js`, supporting JavaScript modules, source maps, and `/static/*` media. | Keep FastAPI as the Python local runtime static route. | `tests/test_python_http_server.py` covers the FastAPI route; Docker-backed e2e covers the Python gateway default. |
| `GET /stats/`, generated `client/stats` assets, and maintenance-generated stats data | FastAPI app | Serves the generated `client/stats` tree, including `index.html`, `/stats/css/stats.css`, `/stats/js/stats.js`, and JSON published by `acquire.stats` beneath `/stats/data/`. | Keep FastAPI as the Python local runtime stats route and publish maintenance output into the shared `client/stats/data` tree. | `tests/test_python_http_server.py` covers static assets and generated data; Docker-backed e2e covers the Python gateway default. |
| `POST /server/report-error` | FastAPI app | Accepts form-encoded `message` and `trace`, validates the request size, normalizes embedded newlines for logging, writes request headers to stdout, and returns an empty `200` response. | Keep this route in FastAPI. | `tests/test_python_http_server.py` covers FastAPI behavior; `tests/test_local_ui_e2e.py::test_python_gateway_accepts_report_error_posts` covers the default gateway. |
| `POST /server/set-password` | FastAPI app | Form-decodes `version`, `username`, and `password` with Pydantic payload models, then delegates legacy normalization and error-code decisions to `acquire.auth`. Malformed, uppercase, or non-64-character password hashes return `Errors.GenericError`, not a password-specific validation error. The response has a JSON content type and a stringified error id or `null`. | Keep password setup and user persistence in Python. | `tests/test_auth.py`, `tests/test_python_http_server.py`, and `tests/test_postgres_persistence.py` cover success, whitespace normalization, existing password, invalid username, invalid password hash returning `Errors.GenericError`, version mismatch, database error behavior, and real ORM persistence. |

### SockJS Gateway Responsibilities

| Boundary | Current owner | Current behavior | Python migration target | Coverage |
| --- | --- | --- | --- | --- |
| `/sockjs` protocol endpoints, including `GET /sockjs/info` | FastAPI app | Supports SockJS negotiation for the generated browser client before opening a session websocket. | Keep Python support for the current SockJS negotiation surface until the browser transport changes deliberately. | `tests/test_python_http_server.py` covers negotiation; Docker-backed e2e covers the default Python gateway. |
| `GET /sockjs/.../websocket` | FastAPI app | Accepts SockJS websocket and websocket-raw transports at `/sockjs`. | Keep the Python websocket path speaking the existing client framing. | `tests/test_local_ui_e2e.py` opens websocket connections through the SockJS path. |
| First client data frame | FastAPI app | Treats the first frame as login JSON: `[version, username, password]`. Whitespace is collapsed in all three fields before validation. Malformed JSON or non-string fields that fail normalization close the socket without sending `FatalError`. The forwarded `ip_address` is only `x-real-ip`; local clients without that header currently appear as `null` in later `SetClientIdToData` messages. | Preserve this login contract, malformed-frame close behavior, and IP-address behavior until the client protocol or privacy policy changes deliberately. | `tests/test_auth.py`, `tests/test_python_http_server.py`, Postgres persistence tests, and Docker-backed e2e cover representative login behavior. |
| Version validation | FastAPI app | Rejects login when the normalized client version differs from `server_version` with `Errors.NotUsingLatestVersion`, sends `CommandsToClient.FatalError`, then closes the socket. Local development uses the literal `VERSION`. | Keep the accepted client version explicit while deployment versioning is redesigned. | `tests/test_auth.py` and `tests/test_python_http_server.py` cover mismatch behavior. |
| Username validation | FastAPI app | Requires 1 to 32 printable ASCII characters; otherwise sends `Errors.InvalidUsername` as a fatal error and closes the socket. | Keep legacy username validation until the user model changes deliberately. | `tests/test_auth.py` covers validation branches. |
| Password lookup | FastAPI app | Looks up `user.name` through the Python ORM and enforces password branches before connecting to the game server. No row plus an empty password is allowed without creating a user record; no row plus a non-empty password returns `Errors.ProvidedPassword`. A passwordless existing user allows only an empty password; any non-empty password returns `Errors.ProvidedPassword`. A password-protected user requires a non-empty exact password match; an empty password returns `Errors.MissingPassword`, and any non-empty non-matching string returns `Errors.IncorrectPassword`. Login does not validate password hash format. If the query fails, the gateway sends `FatalError(GenericError)`, closes the socket, and does not create a game-server session. | Keep database lookup and password enforcement in Python. | `tests/test_auth.py`, `tests/test_python_http_server.py`, and `tests/test_postgres_persistence.py` cover the branches. |
| Existing username replacement | FastAPI app and Python game server | Successful password-authenticated users replace an already connected username; passwordless duplicate usernames are rejected by Python with `Errors.UsernameAlreadyInUse`. | Keep the replacement and duplicate-login behavior intact. | Python duplicate-user behavior has unit/integration coverage; authenticated replacement has auth and HTTP coverage. |
| Later client data frames | FastAPI app | Dispatches mapped client payloads to `Client.on_message` and preserves legacy whitespace normalization. Frames received after the login frame but before mapping are silently dropped rather than queued or dispatched. | Keep direct Python dispatch until protocol changes are intentional. | `tests/test_python_server_integration.py`, `tests/test_python_http_server.py`, and e2e workflow tests cover representative gameplay commands and pre-mapping drops. |
| Browser socket close | FastAPI app | Removes gateway mappings and calls the same Python client disconnect behavior when a mapped websocket closes. | Keep direct Python disconnect behavior. | Integration and e2e tests cover disconnect, leave, watch, and rejoin flows. |

### Historical Socket Protocol

The removed Node gateway connected to `python.sock` and sent newline-delimited
records. `acquire.game_server` still contains this parser and the in-process
FastAPI gateway still consumes the same outbound line format from the game
server, so this contract remains useful test documentation until the game
server API is refactored.

| Direction | Record shape | Historical behavior | Current migration note |
| --- | --- | --- | --- |
| Gateway to Python | `connect [username, ip_address, socket_id, replace_existing_user]\n` | Creates a Python `Client`, allocates a client id, emits the gateway connect mapping, and sends initial lobby/game state. | FastAPI now constructs `Client` in-process through `acquire.realtime.SockJSGateway`. |
| Gateway to Python | `disconnect <client_id>\n` | Disconnects the Python client if it still exists. | FastAPI calls gateway disconnect behavior directly. |
| Gateway to Python | `<client_id> <command-json>\n` | Dispatches `CommandsToServer` payloads to the connected Python client. | FastAPI dispatches mapped payloads to `Client.on_message`. |
| Python to gateway | `connect [socket_id, client_id]\n` | Teaches the gateway which browser socket maps to the allocated Python client id. | `acquire.realtime.SockJSGateway` consumes this in-process. |
| Python to gateway | `disconnect <client_id>\n` | Tells the gateway to close the browser socket for a disconnected client. | `acquire.realtime.SockJSGateway` closes the websocket directly. |
| Python to gateway | `<client-id-list> <command-json>\n` | Sends one command batch to one or more browser sockets. | `acquire.realtime.SockJSGateway` queues the same payloads as SockJS frames. |

### Gameplay Commands Already Owned By Python

After login, gameplay commands are handled by `acquire.game_server`:

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

1. Characterization coverage protects auth, `/server/set-password`, malformed
   login handling, database-error handling, and SockJS edge cases.
2. FastAPI owns `/server/report-error`, `/server/set-password`, static routes,
   and the SockJS-compatible websocket path.
3. Python owns password setup, login validation, user lookup,
   duplicate-session policy, and gameplay command delivery.
4. E2E workflows run against the Python gateway by default.
5. The Node gateway and distribution script have been removed. Remaining
   Node.js usage is limited to the npm client asset build helper.
