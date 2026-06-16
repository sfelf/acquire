import time

import pytest
import server


pytestmark = pytest.mark.unit


@pytest.fixture
def reuse_id_manager():
    return server.ReuseIdManager(0)


def test_reuse_id_manager_allocates_incrementing_ids(reuse_id_manager):
    assert reuse_id_manager.get_id() == 1
    assert reuse_id_manager.get_id() == 2
    assert reuse_id_manager.get_id() == 3


def test_reuse_id_manager_rejects_returning_unused_id(reuse_id_manager):
    with pytest.raises(KeyError):
        reuse_id_manager.return_id(1)


def test_reuse_id_manager_reuses_returned_ids_in_order(reuse_id_manager):
    for expected_id in range(1, 11):
        assert reuse_id_manager.get_id() == expected_id

    reuse_id_manager.return_id(7)
    reuse_id_manager.return_id(4)

    assert reuse_id_manager.get_id() == 4
    assert reuse_id_manager.get_id() == 7
    assert reuse_id_manager.get_id() == 11


def test_reuse_id_manager_reuses_all_returned_ids_in_order(reuse_id_manager):
    for _ in range(1, 11):
        reuse_id_manager.get_id()
    for returned_id in range(1, 11):
        reuse_id_manager.return_id(returned_id)

    for expected_id in range(1, 11):
        assert reuse_id_manager.get_id() == expected_id


def test_reuse_id_manager_waits_before_reusing_returned_ids(reuse_id_manager):
    reuse_id_manager.return_wait = 0.0001

    for expected_id in range(1, 11):
        assert reuse_id_manager.get_id() == expected_id

    reuse_id_manager.return_id(7)
    reuse_id_manager.return_id(4)

    assert reuse_id_manager.get_id() == 11
    time.sleep(0.0001)
    assert reuse_id_manager.get_id() == 4
    assert reuse_id_manager.get_id() == 7


def test_reuse_id_manager_reuses_ids_after_staggered_returns(reuse_id_manager):
    reuse_id_manager.return_wait = 0.0001

    assert reuse_id_manager.get_id() == 1
    assert reuse_id_manager.get_id() == 2
    assert reuse_id_manager.get_id() == 3

    reuse_id_manager.return_id(3)
    reuse_id_manager.return_id(2)

    assert reuse_id_manager.get_id() == 4
    time.sleep(0.0001)
    assert reuse_id_manager.get_id() == 2

    reuse_id_manager.return_id(1)
    time.sleep(0.0001)

    assert reuse_id_manager.get_id() == 1
    assert reuse_id_manager.get_id() == 3


def test_increment_id_manager_ignores_returned_ids():
    id_manager = server.IncrementIdManager()

    assert id_manager.get_id() == 1
    assert id_manager.get_id() == 2

    id_manager.return_id(99)

    assert id_manager.get_id() == 3
