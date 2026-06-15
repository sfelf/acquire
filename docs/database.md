# Database Notes

MySQL is the current database and should remain in place until test coverage is strong.

## Current State

- Python database models live in `server/orm.py`.
- Schema initialization lives in `server/initialize_database.py`.
- Some user and auth queries live in the Node.js server.
- Credentials, database names, and socket paths are currently hard-coded.

## Modernization Direction

1. Add MySQL-backed integration tests with Docker Compose.
2. Move configuration to environment variables.
3. Add migrations, likely with Alembic.
4. Move Node-owned database behavior into Python.
5. Plan the MySQL-to-Postgres migration after regression coverage exists.
