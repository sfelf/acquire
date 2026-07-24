import pytest

import server
from acquire.enums import CommandsToClient, GameBoardTypes, ScoreSheetIndexes, ScoreSheetRows

pytestmark = pytest.mark.unit


class RecordingGame:
    def __init__(self):
        self.client_ids = {1, 2}
        self.pending_messages = []
        self.game_board = None
        self.game_id = "game-1"
        self.internal_game_id = 123
        self.logging_enabled = False

    def add_pending_messages(self, messages, client_ids=None):
        self.pending_messages.append((messages, client_ids))


class FakeGameBoard:
    def __init__(self, active_chain_ids=()):
        self.board_type_to_coordinates = [set() for _ in range(GameBoardTypes.Max.value)]
        for chain_id in active_chain_ids:
            self.board_type_to_coordinates[chain_id].add((chain_id, 0))


def make_player_data(*share_rows):
    player_data = []
    for player_index, shares in enumerate(share_rows):
        row = [0, 0, 0, 0, 0, 0, 0, 60, 60, f"player_{player_index}", None, None]
        for chain_id, share_count in shares.items():
            row[chain_id] = share_count
        player_data.append(row)
    return player_data


def make_score_sheet(player_data=()):
    game = RecordingGame()
    score_sheet = server.ScoreSheet(game)
    score_sheet.player_data = list(player_data)
    return game, score_sheet


def test_adjust_player_data_updates_shares_available_and_emits_message():
    game, score_sheet = make_score_sheet(make_player_data({GameBoardTypes.Luxor.value: 2})[0:1])

    score_sheet.adjust_player_data(0, ScoreSheetIndexes.Luxor.value, 3)

    assert score_sheet.player_data[0][ScoreSheetIndexes.Luxor.value] == 5
    assert score_sheet.available[GameBoardTypes.Luxor.value] == 22
    assert game.pending_messages == [
        (
            [[CommandsToClient.SetScoreSheetCell.value, 0, ScoreSheetIndexes.Luxor.value, 5]],
            {1, 2},
        )
    ]


def test_adjust_player_data_does_not_update_share_availability_for_cash():
    game, score_sheet = make_score_sheet(make_player_data({})[0:1])

    score_sheet.adjust_player_data(0, ScoreSheetIndexes.Cash.value, -12)

    assert score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] == 48
    assert score_sheet.available == [25, 25, 25, 25, 25, 25, 25]
    assert game.pending_messages == [
        (
            [[CommandsToClient.SetScoreSheetCell.value, 0, ScoreSheetIndexes.Cash.value, 48]],
            {1, 2},
        )
    ]


@pytest.mark.parametrize(
    ("chain_id", "chain_size", "expected_price"),
    [
        (GameBoardTypes.Luxor.value, 0, 0),
        (GameBoardTypes.Luxor.value, 2, 2),
        (GameBoardTypes.Luxor.value, 6, 6),
        (GameBoardTypes.Luxor.value, 11, 7),
        (GameBoardTypes.Luxor.value, 41, 10),
        (GameBoardTypes.American.value, 6, 7),
        (GameBoardTypes.Continental.value, 6, 8),
    ],
)
def test_set_chain_size_updates_price_tiers(chain_id, chain_size, expected_price):
    game, score_sheet = make_score_sheet()

    score_sheet.set_chain_size(chain_id, chain_size)

    assert score_sheet.chain_size[chain_id] == chain_size
    assert score_sheet.price[chain_id] == expected_price
    assert game.pending_messages == [
        (
            [
                [
                    CommandsToClient.SetScoreSheetCell.value,
                    ScoreSheetRows.ChainSize.value,
                    chain_id,
                    chain_size,
                ]
            ],
            {1, 2},
        )
    ]


def test_get_bonuses_awards_both_bonuses_to_only_shareholder():
    _game, score_sheet = make_score_sheet(make_player_data({GameBoardTypes.Luxor.value: 3}, {}, {}))
    score_sheet.price[GameBoardTypes.Luxor.value] = 4

    assert score_sheet.get_bonuses(GameBoardTypes.Luxor.value) == [
        [{0}, 60],
    ]


def test_get_bonuses_splits_combined_bonus_for_first_place_tie():
    _game, score_sheet = make_score_sheet(
        make_player_data(
            {GameBoardTypes.Luxor.value: 3},
            {GameBoardTypes.Luxor.value: 3},
            {GameBoardTypes.Luxor.value: 1},
        )
    )
    score_sheet.price[GameBoardTypes.Luxor.value] = 5

    assert score_sheet.get_bonuses(GameBoardTypes.Luxor.value) == [
        [{0, 1}, 38],
    ]


def test_get_bonuses_awards_first_and_splits_second_place_tie():
    _game, score_sheet = make_score_sheet(
        make_player_data(
            {GameBoardTypes.Luxor.value: 4},
            {GameBoardTypes.Luxor.value: 2},
            {GameBoardTypes.Luxor.value: 2},
        )
    )
    score_sheet.price[GameBoardTypes.Luxor.value] = 5

    assert score_sheet.get_bonuses(GameBoardTypes.Luxor.value) == [
        [{0}, 50],
        [{1, 2}, 13],
    ]


def test_update_net_worths_counts_cash_stock_value_and_active_chain_bonuses():
    game, score_sheet = make_score_sheet(
        make_player_data(
            {GameBoardTypes.Luxor.value: 4},
            {GameBoardTypes.Luxor.value: 2},
        )
    )
    game.game_board = FakeGameBoard(active_chain_ids=[GameBoardTypes.Luxor.value])
    score_sheet.price[GameBoardTypes.Luxor.value] = 5

    score_sheet.update_net_worths()

    assert score_sheet.player_data[0][ScoreSheetIndexes.Net.value] == 130
    assert score_sheet.player_data[1][ScoreSheetIndexes.Net.value] == 95


def test_update_net_worths_counts_inactive_chain_stock_without_bonuses():
    game, score_sheet = make_score_sheet(make_player_data({GameBoardTypes.Luxor.value: 4}))
    game.game_board = FakeGameBoard()
    score_sheet.price[GameBoardTypes.Luxor.value] = 5

    score_sheet.update_net_worths()

    assert score_sheet.player_data[0][ScoreSheetIndexes.Net.value] == 80


def test_join_game_updates_shifted_player_ids_and_sends_prior_position_tiles():
    game, score_sheet = make_score_sheet()
    first_client = type("Client", (), {"username": "alice", "client_id": 10})()
    second_client = type("Client", (), {"username": "bob", "client_id": 20})()

    score_sheet.join_game(first_client, (5, 5))
    game.pending_messages.clear()
    score_sheet.join_game(second_client, (1, 1))

    assert first_client.player_id == 1
    assert second_client.player_id == 0
    assert score_sheet.creator_username == "alice"
    assert score_sheet.username_to_player_id == {"alice": 1, "bob": 0}
    assert game.pending_messages == [
        (
            [[CommandsToClient.SetGamePlayerJoin.value, "game-1", 0, 20]],
            None,
        ),
        (
            [
                [
                    CommandsToClient.SetGameBoardCell.value,
                    5,
                    5,
                    GameBoardTypes.NothingYet.value,
                ]
            ],
            {20},
        ),
    ]


def test_join_game_leaves_disconnected_existing_player_without_client_update():
    game, score_sheet = make_score_sheet([[0, 0, 0, 0, 0, 0, 0, 60, 60, "alice", (5, 5), None]])
    score_sheet.creator_username = "alice"
    score_sheet.username_to_player_id = {"alice": 0}
    client = type("Client", (), {"username": "bob", "client_id": 20})()

    score_sheet.join_game(client, (1, 1))

    assert client.player_id == 0
    assert score_sheet.player_data[1][ScoreSheetIndexes.Client.value] is None
    assert score_sheet.username_to_player_id == {"alice": 1, "bob": 0}
