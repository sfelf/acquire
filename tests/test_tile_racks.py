import pytest

import server
from acquire.enums import CommandsToClient, GameBoardTypes, GameHistoryMessages

pytestmark = pytest.mark.unit


class RecordingClient:
    def __init__(self, client_id):
        self.client_id = client_id


class RecordingGame:
    def __init__(self, board=None):
        self.num_players = 1
        self.tile_bag = []
        self.pending_messages = []
        self.history_messages = []
        self.game_board = server.GameBoard(self, board)
        self.score_sheet = type("ScoreSheet", (), {})()
        self.score_sheet.player_data = [
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "player_0", None, RecordingClient(10)]
        ]

    @property
    def client_ids(self):
        return {10}

    def add_pending_messages(self, messages, client_ids=None):
        self.pending_messages.append((messages, client_ids))

    def add_history_message(self, *args, **kwargs):
        self.history_messages.append((args, kwargs))


def make_empty_board():
    return [[GameBoardTypes.Nothing.value for _y in range(9)] for _x in range(12)]


def make_tile_racks(game, rack):
    tile_racks = server.TileRacks.__new__(server.TileRacks)
    tile_racks.game = game
    tile_racks.racks = [rack]
    return tile_racks


def test_init_fills_player_racks_from_tile_bag_end():
    game = RecordingGame()
    game.num_players = 2
    game.tile_bag = [(1, 1), (2, 2)]

    tile_racks = server.TileRacks(game)

    assert tile_racks.racks == [
        [[(2, 2), None, False], [(1, 1), None, True], None, None, None, None],
        [None, None, None, None, None, None],
    ]
    assert game.tile_bag == []


def test_remove_tile_clears_rack_slot_and_are_racks_empty_reflects_contents():
    game = RecordingGame()
    tile_racks = make_tile_racks(game, [[(1, 1), None, False], None, None, None, None, None])

    assert not tile_racks.are_racks_empty()

    tile_racks.remove_tile(0, 0)

    assert tile_racks.racks == [[None, None, None, None, None, None]]
    assert tile_racks.are_racks_empty()


def test_determine_tile_game_board_types_marks_isolated_tile_as_lonely_and_reports_draw():
    game = RecordingGame()
    tile_racks = make_tile_racks(game, [[(1, 1), None, True], None, None, None, None, None])

    tile_racks.determine_tile_game_board_types()

    assert tile_racks.racks[0][0] == [
        (1, 1),
        GameBoardTypes.WillPutLonelyTileDown.value,
        False,
    ]
    assert game.history_messages == [
        ((GameHistoryMessages.DrewTile.value, 0, 1, 1), {"player_id": 0}),
        ((GameHistoryMessages.DrewLastTile.value, 0), {}),
    ]
    assert game.pending_messages == [
        (
            [[CommandsToClient.SetTile.value, 0, 1, 1, GameBoardTypes.WillPutLonelyTileDown.value]],
            {10},
        )
    ]


def test_determine_tile_game_board_types_records_draw_without_connected_client():
    game = RecordingGame()
    game.score_sheet.player_data[0][-1] = None
    tile_racks = make_tile_racks(game, [[(0, 0), None, False], None, None, None, None, None])

    tile_racks.determine_tile_game_board_types()

    assert tile_racks.racks[0][0][1] == GameBoardTypes.WillPutLonelyTileDown.value
    assert game.history_messages == [
        ((GameHistoryMessages.DrewTile.value, 0, 0, 0), {"player_id": 0}),
    ]
    assert game.pending_messages == []


def test_determine_tile_game_board_types_marks_adjacent_lonely_tiles_as_neighbors():
    game = RecordingGame()
    tile_racks = make_tile_racks(
        game,
        [
            [(1, 1), None, False],
            [(1, 2), None, False],
            None,
            None,
            None,
            None,
        ],
    )

    tile_racks.determine_tile_game_board_types()

    assert tile_racks.racks[0][0][1] == GameBoardTypes.HaveNeighboringTileToo.value
    assert tile_racks.racks[0][1][1] == GameBoardTypes.HaveNeighboringTileToo.value


def test_determine_tile_game_board_types_uses_neighboring_chain_type():
    board = make_empty_board()
    board[1][1] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    tile_racks = make_tile_racks(game, [[(1, 2), None, False], None, None, None, None, None])

    tile_racks.determine_tile_game_board_types()

    assert tile_racks.racks[0][0][1] == GameBoardTypes.Luxor.value


def test_determine_tile_game_board_types_blocks_new_chain_when_all_chains_active():
    board = make_empty_board()
    for chain_id in range(7):
        board[chain_id][0] = chain_id
    board[1][1] = GameBoardTypes.NothingYet.value
    game = RecordingGame(board)
    tile_racks = make_tile_racks(game, [[(1, 2), None, False], None, None, None, None, None])

    tile_racks.determine_tile_game_board_types()

    assert tile_racks.racks[0][0][1] == GameBoardTypes.CantPlayNow.value


def test_determine_tile_game_board_types_marks_safe_chain_merge_as_unplayable():
    board = make_empty_board()
    for y in range(9):
        board[0][y] = GameBoardTypes.Luxor.value
        board[2][y] = GameBoardTypes.Tower.value
    board[1][0] = GameBoardTypes.Luxor.value
    board[1][1] = GameBoardTypes.Luxor.value
    board[3][0] = GameBoardTypes.Tower.value
    board[3][1] = GameBoardTypes.Tower.value
    game = RecordingGame(board)
    tile_racks = make_tile_racks(game, [[(1, 7), None, False], None, None, None, None, None])

    tile_racks.determine_tile_game_board_types()

    assert tile_racks.racks[0][0][1] == GameBoardTypes.CantPlayEver.value


def test_determine_tile_game_board_types_updates_existing_tile_type():
    board = make_empty_board()
    board[1][0] = GameBoardTypes.Luxor.value
    game = RecordingGame(board)
    tile_racks = make_tile_racks(
        game,
        [[(0, 0), GameBoardTypes.WillPutLonelyTileDown.value, False], None, None, None, None, None],
    )

    tile_racks.determine_tile_game_board_types()

    assert tile_racks.racks[0][0][1] == GameBoardTypes.Luxor.value
    assert game.pending_messages == [
        (
            [[CommandsToClient.SetTileGameBoardType.value, 0, GameBoardTypes.Luxor.value]],
            {10},
        )
    ]


def test_replace_dead_tiles_removes_marks_and_draws_replacement_tile():
    game = RecordingGame()
    game.tile_bag = [(2, 2)]
    tile_racks = make_tile_racks(
        game,
        [[(1, 7), GameBoardTypes.CantPlayEver.value, False], None, None, None, None, None],
    )

    tile_racks.replace_dead_tiles(0)

    assert game.game_board.x_to_y_to_board_type[1][7] == GameBoardTypes.CantPlayEver.value
    assert tile_racks.racks[0][0][0] == (2, 2)
    assert game.pending_messages[0] == (
        [[CommandsToClient.RemoveTile.value, 0]],
        {10},
    )
    assert game.history_messages[0] == (
        (GameHistoryMessages.ReplacedDeadTile.value, 0, 1, 7),
        {},
    )
