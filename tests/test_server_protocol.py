import server


class RecordingClient:
    def __init__(self):
        self.messages = []
        self.disconnects = 0

    def on_message(self, value):
        self.messages.append(value)

    def disconnect(self):
        self.disconnects += 1


class RecordingTransport:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)


def test_protocol_buffers_partial_messages(monkeypatch):
    created_clients = []
    game_server = server.Server()
    protocol = server.ServerProtocol(game_server)

    def create_client(*args):
        created_clients.append(args)

    monkeypatch.setattr(server, "Client", create_client)

    protocol.data_received(b'connect ["alice","127.0.0.1",')

    assert created_clients == []
    assert protocol.unprocessed_data == [b'connect ["alice","127.0.0.1",']

    protocol.data_received(b'"socket-1",false]\n')

    assert created_clients == [(game_server, "alice", "127.0.0.1", "socket-1", False)]
    assert protocol.unprocessed_data == []


def test_protocol_routes_client_messages_and_disconnects():
    game_server = server.Server()
    protocol = server.ServerProtocol(game_server)
    client = RecordingClient()
    game_server.client_id_to_client[42] = client

    protocol.data_received(b'42 ["message"]\ndisconnect 42\n')

    assert client.messages == [b'["message"]']
    assert client.disconnects == 1


def test_protocol_ignores_messages_for_unknown_clients():
    game_server = server.Server()
    protocol = server.ServerProtocol(game_server)

    protocol.data_received(b'999 ["message"]\ndisconnect 999\n')

    assert game_server.client_id_to_client == {}


def test_connection_made_sets_transport_writer():
    game_server = server.Server()
    protocol = server.ServerProtocol(game_server)
    transport = RecordingTransport()

    protocol.connection_made(transport)
    game_server.transport_write(b"hello")

    assert protocol.transport is transport
    assert transport.writes == [b"hello"]
