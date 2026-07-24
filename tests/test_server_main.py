import pytest

from acquire import game_server as server

pytestmark = pytest.mark.unit


def test_main_starts_unix_server_and_schedules_expiration_loop(monkeypatch):
    created_servers = []

    class FakeGameServer:
        def __init__(self):
            self.destroy_calls = 0

        def destroy_expired_games(self):
            self.destroy_calls += 1

    class FakeLoop:
        def __init__(self):
            self.scheduled = []
            self.run_until_complete_calls = []

        def create_unix_server(self, protocol_factory, path):
            created_servers.append((protocol_factory(), path))
            return "created-server"

        def run_until_complete(self, value):
            self.run_until_complete_calls.append(value)

        def call_later(self, delay, callback):
            self.scheduled.append((delay, callback))

        def run_forever(self):
            raise KeyboardInterrupt

    fake_server = FakeGameServer()
    fake_loop = FakeLoop()
    monkeypatch.setattr(server, "Server", lambda: fake_server)
    monkeypatch.setattr(server.asyncio, "get_event_loop", lambda: fake_loop)

    server.main()
    fake_loop.scheduled[0][1]()

    assert created_servers[0][1] == "python.sock"
    assert isinstance(created_servers[0][0], server.ServerProtocol)
    assert fake_loop.run_until_complete_calls == ["created-server"]
    assert [delay for delay, _callback in fake_loop.scheduled] == [15, 15]
    assert fake_server.destroy_calls == 1


def test_main_prints_unexpected_loop_errors(monkeypatch, capsys):
    class FakeLoop:
        def create_unix_server(self, protocol_factory, path):
            return "created-server"

        def run_until_complete(self, value):
            pass

        def call_later(self, delay, callback):
            pass

        def run_forever(self):
            raise RuntimeError("loop failed")

    monkeypatch.setattr(server.asyncio, "get_event_loop", lambda: FakeLoop())

    server.main()

    assert "RuntimeError: loop failed" in capsys.readouterr().err
