import pytest

import server

pytestmark = pytest.mark.unit


def test_add_pending_messages_splits_overlapping_client_groups():
    game_server = server.Server()
    game_server.add_pending_messages([["first"]], {1, 2})
    game_server.add_pending_messages([["second"]], {2, 3})

    assert game_server.client_ids_and_messages == [
        [{2}, [["first"], ["second"]]],
        [{1}, [["first"]]],
        [{3}, [["second"]]],
    ]


def test_add_pending_messages_defaults_to_all_connected_clients():
    game_server = server.Server()
    game_server.client_ids = {3, 1}

    game_server.add_pending_messages([["broadcast"]])

    assert game_server.client_ids_and_messages == [
        [{1, 3}, [["broadcast"]]],
    ]


def test_flush_pending_messages_writes_sorted_client_ids_and_clears_queue():
    writes = []
    game_server = server.Server()
    game_server.transport_write = writes.append
    game_server.add_pending_messages([[1, "first"]], {3, 1})
    game_server.add_pending_messages([[2, "second"]], {2})

    game_server.flush_pending_messages()

    assert writes == [
        b'1,3 [[1,"first"]]\n2 [[2,"second"]]\n',
    ]
    assert game_server.client_ids_and_messages == []
