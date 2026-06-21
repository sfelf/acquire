import pytest
import websocket_gateway

pytestmark = pytest.mark.unit


def test_decode_sockjs_frame_returns_empty_messages_for_heartbeats():
    assert websocket_gateway.decode_sockjs_frame("h") == []


@pytest.mark.parametrize("frame", ['{"message":"hello"}', "[1]", "not json"])
def test_decode_sockjs_frame_rejects_invalid_application_frames(frame):
    with pytest.raises(ValueError):
        websocket_gateway.decode_sockjs_frame(frame)


def test_normalize_client_payload_matches_legacy_gateway_whitespace_collapse():
    assert websocket_gateway.normalize_client_payload('[6,\n"hello\tthere"]') == (
        '[6, "hello there"]'
    )


def test_sockjs_gateway_ignores_unmapped_transport_lines():
    gateway = websocket_gateway.SockJSGateway()
    connection = gateway.new_connection("socket-1", object())

    gateway.receive_client_payload(connection, "[6, \"ignored before login\"]")
    gateway.write_from_game_server(
        b'\nconnect ["missing-socket",1]\ndisconnect 2\n1 [[21,1,"hello"]]\n'
    )

    assert connection.client_id is None
    assert connection.outbound_frames.empty()


def test_sockjs_gateway_maps_connects_messages_and_disconnects():
    gateway = websocket_gateway.SockJSGateway()
    connection = gateway.new_connection("socket-1", object())

    gateway.write_from_game_server(
        b'connect ["socket-1",1]\n1,2 [[21,1,"hello"]]\ndisconnect 1\n'
    )

    assert connection.client_id == 1
    assert gateway.client_id_to_connection[1] is connection
    assert connection.outbound_frames.get_nowait() == websocket_gateway.encode_sockjs_messages(
        '[[21,1,"hello"]]'
    )
    assert connection.outbound_frames.get_nowait() is None
