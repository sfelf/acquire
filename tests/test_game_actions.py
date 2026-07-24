import pytest

import server
from acquire.enums import (
    CommandsToClient,
    GameActions,
    GameBoardTypes,
    GameHistoryMessages,
    GameModes,
    GameStates,
    ScoreSheetIndexes,
)

pytestmark = pytest.mark.unit


class RecordingGame:
    def __init__(self, board=None):
        self.num_players = 2
        self.client_ids = {10, 11}
        self.pending_messages = []
        self.history_messages = []
        self.state_changes = []
        self.turn_player_id = None
        self.turns_without_played_tiles_count = 0
        self.mode = GameModes.Singles.value
        self.game_board = server.GameBoard(self, board)
        self.score_sheet = server.ScoreSheet(self)
        self.score_sheet.player_data = [
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "player_0", None, None],
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "player_1", None, None],
        ]
        self.tile_racks = RecordingTileRacks()
        self.tile_bag = [(x, y) for x in range(12) for y in range(9)]

    def add_pending_messages(self, messages, client_ids=None):
        self.pending_messages.append((messages, client_ids))

    def add_history_message(self, *args, **kwargs):
        self.history_messages.append((args, kwargs))

    def set_state(self, state, mode=None, max_players=None):
        self.state_changes.append((state, mode, max_players))


class RecordingTileRacks:
    def __init__(self, racks=None):
        self.racks = racks if racks is not None else [[None] * 6, [None] * 6]
        self.removed_tiles = []
        self.determine_calls = []
        self.draw_calls = []
        self.replace_dead_tiles_calls = []
        self.empty_results = [False]

    def remove_tile(self, player_id, tile_index):
        self.removed_tiles.append((player_id, tile_index))
        self.racks[player_id][tile_index] = None

    def determine_tile_game_board_types(self, player_ids=None):
        self.determine_calls.append(player_ids)

    def draw_tile(self, player_id):
        self.draw_calls.append(player_id)

    def replace_dead_tiles(self, player_id):
        self.replace_dead_tiles_calls.append(player_id)

    def are_racks_empty(self):
        if len(self.empty_results) > 1:
            return self.empty_results.pop(0)
        return self.empty_results[0]


def make_empty_board():
    return [[GameBoardTypes.Nothing.value for _y in range(9)] for _x in range(12)]


def test_action_send_message_includes_action_and_player_ids():
    game = RecordingGame()
    action = server.ActionPlayTile(game, 1)

    action.send_message({11})

    assert game.pending_messages == [
        ([[CommandsToClient.SetGameAction.value, GameActions.PlayTile.value, 1]], {11})
    ]


def test_base_action_prepare_is_noop():
    game = RecordingGame()

    assert server.Action(game, 0, GameActions.StartGame.value).prepare() is None


def test_play_tile_prepare_sets_turn_and_resets_no_tile_counter_when_playable():
    game = RecordingGame()
    game.turns_without_played_tiles_count = 2
    game.tile_racks.racks[0][0] = [
        (1, 1),
        GameBoardTypes.WillPutLonelyTileDown.value,
        False,
    ]

    result = server.ActionPlayTile(game, 0).prepare()

    assert result is None
    assert game.turn_player_id == 0
    assert game.turns_without_played_tiles_count == 0
    assert game.pending_messages == [([[CommandsToClient.SetTurn.value, 0]], {10, 11})]
    assert game.history_messages == [((GameHistoryMessages.TurnBegan.value, 0), {})]


def test_play_tile_prepare_skips_turn_when_player_has_no_playable_tiles():
    game = RecordingGame()
    game.tile_racks.racks[0][0] = [
        (1, 1),
        GameBoardTypes.CantPlayNow.value,
        False,
    ]
    game.tile_racks.racks[0][1] = [
        (1, 2),
        GameBoardTypes.CantPlayEver.value,
        False,
    ]

    result = server.ActionPlayTile(game, 0).prepare()

    assert result is True
    assert game.turns_without_played_tiles_count == 1
    assert game.history_messages == [
        ((GameHistoryMessages.TurnBegan.value, 0), {}),
        ((GameHistoryMessages.HasNoPlayableTile.value, 0), {}),
    ]


def test_play_tile_execute_places_lonely_tile_and_removes_it_from_rack():
    game = RecordingGame()
    game.tile_racks.racks[0][0] = [
        (1, 1),
        GameBoardTypes.WillPutLonelyTileDown.value,
        False,
    ]

    result = server.ActionPlayTile(game, 0).execute(0)

    assert result is True
    assert game.game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.NothingYet.value
    assert game.tile_racks.removed_tiles == [(0, 0)]
    assert game.history_messages == [((GameHistoryMessages.PlayedTile.value, 0, 1, 1), {})]


def test_play_tile_execute_extends_existing_chain_and_updates_chain_size():
    board = make_empty_board()
    board[1][0] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    game.tile_racks.racks[0][0] = [(1, 1), GameBoardTypes.Luxor.value, False]

    result = server.ActionPlayTile(game, 0).execute(0)

    assert result is True
    assert game.game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.Luxor.value
    assert game.score_sheet.chain_size[GameBoardTypes.Luxor.value] == 2
    assert game.tile_racks.removed_tiles == [(0, 0)]
    assert game.history_messages == [((GameHistoryMessages.PlayedTile.value, 0, 1, 1), {})]


def test_play_tile_execute_returns_new_chain_selection_action():
    game = RecordingGame()
    game.tile_racks.racks[0][0] = [
        (1, 1),
        GameBoardTypes.WillFormNewChain.value,
        False,
    ]
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 2

    result = server.ActionPlayTile(game, 0).execute(0)

    assert len(result) == 1
    next_action = result[0]
    assert isinstance(next_action, server.ActionSelectNewChain)
    assert next_action.game_board_type_ids == [1, 2, 3, 4, 5, 6]
    assert next_action.tile == (1, 1)
    assert game.tile_racks.removed_tiles == [(0, 0)]
    assert game.history_messages == [((GameHistoryMessages.PlayedTile.value, 0, 1, 1), {})]


@pytest.mark.parametrize("tile_index", ["0", -1, 6])
def test_play_tile_execute_ignores_invalid_tile_indexes(tile_index):
    game = RecordingGame()
    game.tile_racks.racks[0][0] = [
        (1, 1),
        GameBoardTypes.WillPutLonelyTileDown.value,
        False,
    ]

    result = server.ActionPlayTile(game, 0).execute(tile_index)

    assert result is None
    assert game.tile_racks.removed_tiles == []
    assert game.history_messages == []


def test_play_tile_execute_ignores_empty_and_unrecognized_rack_slots():
    game = RecordingGame()
    action = server.ActionPlayTile(game, 0)

    assert action.execute(0) is None

    game.tile_racks.racks[0][0] = [
        (1, 1),
        GameBoardTypes.CantPlayNow.value,
        False,
    ]

    assert action.execute(0) is None
    assert game.tile_racks.removed_tiles == []
    assert game.history_messages == []


def test_select_new_chain_prepare_auto_creates_only_available_chain():
    board = make_empty_board()
    board[1][1] = GameBoardTypes.NothingYet.value
    game = RecordingGame(board)

    result = server.ActionSelectNewChain(
        game,
        0,
        [GameBoardTypes.Tower.value],
        (1, 1),
    ).prepare()

    assert result is True
    assert game.game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.Tower.value
    assert game.score_sheet.chain_size[GameBoardTypes.Tower.value] == 1
    assert game.score_sheet.player_data[0][GameBoardTypes.Tower.value] == 1
    assert game.history_messages == [
        ((GameHistoryMessages.FormedChain.value, 0, GameBoardTypes.Tower.value), {})
    ]


def test_select_new_chain_prepare_marks_tile_pending_when_multiple_chains_available():
    game = RecordingGame()

    result = server.ActionSelectNewChain(
        game,
        0,
        [GameBoardTypes.Tower.value, GameBoardTypes.American.value],
        (1, 1),
    ).prepare()

    assert result is None
    assert game.game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.NothingYet.value
    assert game.tile_racks.determine_calls == [None]


def test_select_new_chain_execute_ignores_unavailable_chain_id():
    game = RecordingGame()
    action = server.ActionSelectNewChain(
        game,
        0,
        [GameBoardTypes.Tower.value],
        (1, 1),
    )

    result = action.execute(GameBoardTypes.American.value)

    assert result is None
    assert game.score_sheet.chain_size[GameBoardTypes.Tower.value] == 0
    assert game.history_messages == []


def test_select_new_chain_execute_creates_selected_available_chain():
    board = make_empty_board()
    board[1][1] = GameBoardTypes.NothingYet.value
    game = RecordingGame(board)
    action = server.ActionSelectNewChain(
        game,
        0,
        [GameBoardTypes.Tower.value, GameBoardTypes.American.value],
        (1, 1),
    )

    result = action.execute(GameBoardTypes.American.value)

    assert result is True
    assert game.game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.American.value
    assert game.score_sheet.chain_size[GameBoardTypes.American.value] == 1
    assert game.score_sheet.player_data[0][GameBoardTypes.American.value] == 1
    assert game.history_messages == [
        ((GameHistoryMessages.FormedChain.value, 0, GameBoardTypes.American.value), {})
    ]


def test_select_merger_survivor_prepare_prompts_when_largest_chains_are_tied():
    game = RecordingGame()
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 3
    game.score_sheet.chain_size[GameBoardTypes.Tower.value] = 3
    action = server.ActionSelectMergerSurvivor(
        game,
        0,
        {GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value},
        (1, 1),
    )

    result = action.prepare()

    assert result is None
    assert action.additional_params == [[GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value]]
    assert game.game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.NothingYet.value
    assert game.tile_racks.determine_calls == [None]
    assert game.history_messages == [
        (
            (
                GameHistoryMessages.MergedChains.value,
                0,
                [GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value],
            ),
            {},
        )
    ]


def test_select_merger_survivor_execute_records_selected_survivor():
    board = make_empty_board()
    board[0][1] = GameBoardTypes.Luxor.value
    board[2][1] = GameBoardTypes.Tower.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 1
    game.score_sheet.chain_size[GameBoardTypes.Tower.value] = 1
    game.score_sheet.player_data[0][GameBoardTypes.Tower.value] = 1
    game.score_sheet.price[GameBoardTypes.Tower.value] = 2
    action = server.ActionSelectMergerSurvivor(
        game,
        0,
        {GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value},
        (1, 1),
    )

    result = action.execute(GameBoardTypes.Luxor.value)

    assert len(result) == 1
    assert isinstance(result[0], server.ActionSelectChainToDisposeOfNext)
    assert game.history_messages == [
        (
            (
                GameHistoryMessages.SelectedMergerSurvivor.value,
                0,
                GameBoardTypes.Luxor.value,
            ),
            {},
        ),
        (
            (
                GameHistoryMessages.ReceivedBonus.value,
                0,
                GameBoardTypes.Tower.value,
                30,
            ),
            {},
        ),
    ]


def test_select_merger_survivor_prepare_auto_selects_unique_largest_chain():
    board = make_empty_board()
    board[0][1] = GameBoardTypes.Luxor.value
    board[0][2] = GameBoardTypes.Luxor.value
    board[2][1] = GameBoardTypes.Tower.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.chain_size[GameBoardTypes.Tower.value] = 1
    game.score_sheet.price[GameBoardTypes.Tower.value] = 2
    game.score_sheet.player_data[0][GameBoardTypes.Tower.value] = 2
    game.score_sheet.player_data[1][GameBoardTypes.Tower.value] = 1

    result = server.ActionSelectMergerSurvivor(
        game,
        0,
        {GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value},
        (1, 1),
    ).prepare()

    assert len(result) == 1
    next_action = result[0]
    assert isinstance(next_action, server.ActionSelectChainToDisposeOfNext)
    assert next_action.defunct_type_ids == {GameBoardTypes.Tower.value}
    assert next_action.controlling_type_id == GameBoardTypes.Luxor.value
    assert game.game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.Luxor.value
    assert game.game_board.x_to_y_to_board_type[2][1] == GameBoardTypes.Luxor.value
    assert game.score_sheet.chain_size[GameBoardTypes.Luxor.value] == 4
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] == 80
    assert game.score_sheet.player_data[1][ScoreSheetIndexes.Cash.value] == 70
    assert game.tile_racks.determine_calls == [None]
    assert game.history_messages == [
        (
            (
                GameHistoryMessages.MergedChains.value,
                0,
                [GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value],
            ),
            {},
        ),
        (
            (
                GameHistoryMessages.ReceivedBonus.value,
                0,
                GameBoardTypes.Tower.value,
                20,
            ),
            {},
        ),
        (
            (
                GameHistoryMessages.ReceivedBonus.value,
                1,
                GameBoardTypes.Tower.value,
                10,
            ),
            {},
        ),
    ]


def test_select_chain_to_dispose_prepare_prompts_when_multiple_defunct_chains_remain():
    game = RecordingGame()
    action = server.ActionSelectChainToDisposeOfNext(
        game,
        0,
        {GameBoardTypes.Tower.value, GameBoardTypes.American.value},
        GameBoardTypes.Luxor.value,
    )

    result = action.prepare()

    assert result is None
    assert action.additional_params == [[GameBoardTypes.Tower.value, GameBoardTypes.American.value]]


def test_select_chain_to_dispose_prepare_auto_selects_single_defunct_chain():
    game = RecordingGame()
    game.score_sheet.player_data[1][GameBoardTypes.Tower.value] = 2

    result = server.ActionSelectChainToDisposeOfNext(
        game,
        0,
        {GameBoardTypes.Tower.value},
        GameBoardTypes.Luxor.value,
    ).prepare()

    assert len(result) == 1
    assert isinstance(result[0], server.ActionDisposeOfShares)
    assert result[0].player_id == 1
    assert result[0].defunct_type_id == GameBoardTypes.Tower.value


def test_select_chain_to_dispose_execute_returns_disposal_actions_in_turn_order():
    game = RecordingGame()
    game.score_sheet.player_data[0][GameBoardTypes.Tower.value] = 1
    game.score_sheet.player_data[1][GameBoardTypes.Tower.value] = 2
    action = server.ActionSelectChainToDisposeOfNext(
        game,
        1,
        {GameBoardTypes.Tower.value, GameBoardTypes.American.value},
        GameBoardTypes.Luxor.value,
    )

    result = action.execute(GameBoardTypes.Tower.value)

    assert len(result) == 3
    assert [next_action.player_id for next_action in result[:2]] == [1, 0]
    assert all(isinstance(next_action, server.ActionDisposeOfShares) for next_action in result[:2])
    assert isinstance(result[2], server.ActionSelectChainToDisposeOfNext)
    assert result[2].defunct_type_ids == {GameBoardTypes.American.value}
    assert game.history_messages == [
        (
            (
                GameHistoryMessages.SelectedChainToDisposeOfNext.value,
                1,
                GameBoardTypes.Tower.value,
            ),
            {},
        )
    ]


def test_dispose_of_shares_execute_trades_sells_and_records_history():
    game = RecordingGame()
    game.score_sheet.player_data[0][GameBoardTypes.Tower.value] = 5
    game.score_sheet.available[GameBoardTypes.Luxor.value] = 25
    game.score_sheet.price[GameBoardTypes.Tower.value] = 3
    action = server.ActionDisposeOfShares(
        game,
        0,
        GameBoardTypes.Tower.value,
        GameBoardTypes.Luxor.value,
    )
    action.prepare()

    result = action.execute(2, 3)

    assert result is True
    assert game.score_sheet.player_data[0][GameBoardTypes.Tower.value] == 0
    assert game.score_sheet.player_data[0][GameBoardTypes.Luxor.value] == 1
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] == 69
    assert game.history_messages == [
        (
            (
                GameHistoryMessages.DisposedOfShares.value,
                0,
                GameBoardTypes.Tower.value,
                2,
                3,
            ),
            {},
        )
    ]


def test_dispose_of_shares_execute_records_zero_trade_zero_sale_choice():
    game = RecordingGame()
    game.score_sheet.player_data[0][GameBoardTypes.Tower.value] = 5
    action = server.ActionDisposeOfShares(
        game,
        0,
        GameBoardTypes.Tower.value,
        GameBoardTypes.Luxor.value,
    )
    action.prepare()

    result = action.execute(0, 0)

    assert result is True
    assert game.score_sheet.player_data[0][GameBoardTypes.Tower.value] == 5
    assert game.score_sheet.player_data[0][GameBoardTypes.Luxor.value] == 0
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] == 60
    assert game.history_messages == [
        (
            (
                GameHistoryMessages.DisposedOfShares.value,
                0,
                GameBoardTypes.Tower.value,
                0,
                0,
            ),
            {},
        )
    ]


@pytest.mark.parametrize(
    ("trade_amount", "sell_amount"),
    [
        (1, 0),
        (-2, 0),
        (4, 0),
        (2, -1),
        (2, 4),
        ("2", 0),
        (0, "1"),
    ],
)
def test_dispose_of_shares_execute_ignores_invalid_amounts(trade_amount, sell_amount):
    game = RecordingGame()
    game.score_sheet.player_data[0][GameBoardTypes.Tower.value] = 5
    game.score_sheet.available[GameBoardTypes.Luxor.value] = 1
    action = server.ActionDisposeOfShares(
        game,
        0,
        GameBoardTypes.Tower.value,
        GameBoardTypes.Luxor.value,
    )
    action.prepare()

    result = action.execute(trade_amount, sell_amount)

    assert result is None
    assert game.score_sheet.player_data[0][GameBoardTypes.Tower.value] == 5
    assert game.score_sheet.player_data[0][GameBoardTypes.Luxor.value] == 0
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] == 60
    assert game.history_messages == []


def test_purchase_shares_prepare_keeps_action_pending_when_player_can_buy():
    board = make_empty_board()
    board[0][0] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.price[GameBoardTypes.Luxor.value] = 2

    result = server.ActionPurchaseShares(game, 0).prepare()

    assert result is None
    assert game.tile_racks.determine_calls == [None]
    assert game.tile_racks.draw_calls == []
    assert game.history_messages == []


def test_purchase_shares_prepare_clears_stale_chain_size_when_board_is_empty():
    game = RecordingGame()
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 3
    action = server.ActionPurchaseShares(game, 0)

    result = action.prepare()

    assert [type(next_action) for next_action in result] == [
        server.ActionPlayTile,
        server.ActionPurchaseShares,
    ]
    assert game.score_sheet.chain_size[GameBoardTypes.Luxor.value] == 0


def test_purchase_shares_prepare_completes_turn_when_player_cannot_afford_available_shares():
    board = make_empty_board()
    board[0][0] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.price[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] = 1

    result = server.ActionPurchaseShares(game, 0).prepare()

    assert [type(action) for action in result] == [
        server.ActionPlayTile,
        server.ActionPurchaseShares,
    ]
    assert [action.player_id for action in result] == [1, 1]
    assert game.tile_racks.determine_calls == [None, [0]]
    assert game.tile_racks.draw_calls == [0]
    assert game.tile_racks.replace_dead_tiles_calls == [0]
    assert game.history_messages == [((GameHistoryMessages.CouldNotAffordAnyShares.value, 0), {})]


def test_purchase_shares_execute_buys_shares_and_advances_to_next_player():
    board = make_empty_board()
    board[0][0] = GameBoardTypes.Luxor.value
    board[1][0] = GameBoardTypes.Tower.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.chain_size[GameBoardTypes.Tower.value] = 3
    game.score_sheet.price[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.price[GameBoardTypes.Tower.value] = 3
    action = server.ActionPurchaseShares(game, 0)

    result = action.execute(
        [GameBoardTypes.Luxor.value, GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value],
        0,
    )

    assert [type(next_action) for next_action in result] == [
        server.ActionPlayTile,
        server.ActionPurchaseShares,
    ]
    assert [next_action.player_id for next_action in result] == [1, 1]
    assert game.score_sheet.player_data[0][GameBoardTypes.Luxor.value] == 2
    assert game.score_sheet.player_data[0][GameBoardTypes.Tower.value] == 1
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] == 53
    assert game.tile_racks.draw_calls == [0]
    assert game.tile_racks.determine_calls == [[0]]
    assert game.tile_racks.replace_dead_tiles_calls == [0]
    assert game.history_messages == [
        (
            (
                GameHistoryMessages.PurchasedShares.value,
                0,
                [[GameBoardTypes.Luxor.value, 2], [GameBoardTypes.Tower.value, 1]],
            ),
            {},
        )
    ]


@pytest.mark.parametrize(
    ("game_board_type_ids", "end_game"),
    [
        ([GameBoardTypes.Luxor.value] * 4, 0),
        ([GameBoardTypes.Luxor.value], 2),
        ("not-a-list", 0),
        ([GameBoardTypes.Nothing.value], 0),
        ([GameBoardTypes.Tower.value], 0),
    ],
)
def test_purchase_shares_execute_ignores_invalid_purchase_requests(
    game_board_type_ids,
    end_game,
):
    board = make_empty_board()
    board[0][0] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.price[GameBoardTypes.Luxor.value] = 2
    action = server.ActionPurchaseShares(game, 0)

    result = action.execute(game_board_type_ids, end_game)

    assert result is None
    assert game.score_sheet.player_data[0][GameBoardTypes.Luxor.value] == 0
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] == 60
    assert game.history_messages == []
    assert game.tile_racks.draw_calls == []


def test_purchase_shares_execute_ignores_purchase_player_cannot_afford():
    board = make_empty_board()
    board[0][0] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.price[GameBoardTypes.Luxor.value] = 61

    result = server.ActionPurchaseShares(game, 0).execute([GameBoardTypes.Luxor.value], 0)

    assert result is None
    assert game.score_sheet.player_data[0][GameBoardTypes.Luxor.value] == 0
    assert game.score_sheet.player_data[0][ScoreSheetIndexes.Cash.value] == 60
    assert game.history_messages == []


def test_purchase_shares_execute_can_end_game_when_chain_is_large_enough():
    board = make_empty_board()
    for y in range(9):
        board[0][y] = GameBoardTypes.Luxor.value
        board[1][y] = GameBoardTypes.Luxor.value
        board[2][y] = GameBoardTypes.Luxor.value
        board[3][y] = GameBoardTypes.Luxor.value
        board[4][y] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 41
    game.score_sheet.price[GameBoardTypes.Luxor.value] = 8
    action = server.ActionPurchaseShares(game, 0)
    action.prepare()

    result = action.execute([], 1)

    assert len(result) == 1
    assert isinstance(result[0], server.ActionGameOver)
    assert result[0].player_id == 0
    assert game.turn_player_id is None
    assert game.pending_messages[-1] == (
        [[CommandsToClient.SetTurn.value, None]],
        {10, 11},
    )
    assert game.state_changes == [(GameStates.Completed.value, None, None)]
    assert game.history_messages == [
        ((GameHistoryMessages.PurchasedShares.value, 0, []), {}),
        ((GameHistoryMessages.EndedGame.value, 0), {}),
    ]


def test_purchase_shares_execute_ignores_end_game_flag_when_not_allowed():
    board = make_empty_board()
    board[0][0] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    game.score_sheet.chain_size[GameBoardTypes.Luxor.value] = 2
    game.score_sheet.price[GameBoardTypes.Luxor.value] = 2
    action = server.ActionPurchaseShares(game, 0)
    action.prepare()

    result = action.execute([], 1)

    assert [type(next_action) for next_action in result] == [
        server.ActionPlayTile,
        server.ActionPurchaseShares,
    ]
    assert game.state_changes == []
    assert game.history_messages == [((GameHistoryMessages.PurchasedShares.value, 0, []), {})]


def test_purchase_shares_complete_action_ends_game_when_all_tiles_are_played():
    game = RecordingGame()
    game.tile_racks.empty_results = [True]

    result = server.ActionPurchaseShares(game, 0)._complete_action()

    assert len(result) == 1
    assert isinstance(result[0], server.ActionGameOver)
    assert game.history_messages == [((GameHistoryMessages.AllTilesPlayed.value, None), {})]
    assert game.state_changes == [(GameStates.Completed.value, None, None)]


def test_purchase_shares_complete_action_ends_game_after_round_without_played_tiles():
    game = RecordingGame()
    game.turns_without_played_tiles_count = game.num_players

    result = server.ActionPurchaseShares(game, 0)._complete_action()

    assert len(result) == 1
    assert isinstance(result[0], server.ActionGameOver)
    assert game.history_messages == [
        ((GameHistoryMessages.NoTilesPlayedForEntireRound.value, None), {})
    ]
    assert game.state_changes == [(GameStates.Completed.value, None, None)]


def test_purchase_shares_complete_action_ends_when_draw_empties_racks():
    game = RecordingGame()
    game.tile_racks.empty_results = [False, True]

    result = server.ActionPurchaseShares(game, 0)._complete_action()

    assert len(result) == 1
    assert isinstance(result[0], server.ActionGameOver)
    assert game.tile_racks.draw_calls == [0]
    assert game.tile_racks.determine_calls == [[0]]
    assert game.tile_racks.replace_dead_tiles_calls == [0]
    assert game.history_messages == [((GameHistoryMessages.AllTilesPlayed.value, None), {})]


def test_start_game_downgrades_short_teams_game_to_singles():
    game = RecordingGame()
    game.mode = GameModes.Teams.value
    game.num_players = 2
    game.tile_bag = [(x, y) for x in range(12) for y in range(9)]

    result = server.ActionStartGame(game, 0).execute()

    assert [type(next_action) for next_action in result] == [
        server.ActionPlayTile,
        server.ActionPurchaseShares,
    ]
    assert game.state_changes[0] == (
        GameStates.InProgress.value,
        GameModes.Singles.value,
        None,
    )
    assert isinstance(game.tile_racks, server.TileRacks)


def test_start_game_keeps_full_teams_game_in_teams_mode():
    game = RecordingGame()
    game.mode = GameModes.Teams.value
    game.num_players = 4
    game.score_sheet.player_data.extend(
        [
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "player_2", None, None],
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "player_3", None, None],
        ]
    )
    game.tile_bag = [(x, y) for x in range(12) for y in range(9)]

    result = server.ActionStartGame(game, 0).execute()

    assert [type(next_action) for next_action in result] == [
        server.ActionPlayTile,
        server.ActionPurchaseShares,
    ]
    assert game.state_changes[0] == (GameStates.InProgress.value, None, None)
    assert isinstance(game.tile_racks, server.TileRacks)
