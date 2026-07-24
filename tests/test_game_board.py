import pytest

import server
from acquire.enums import CommandsToClient, GameBoardTypes

pytestmark = pytest.mark.unit


class RecordingGame:
    def __init__(self):
        self.client_ids = {1, 2}
        self.pending_messages = []

    def add_pending_messages(self, messages, client_ids=None):
        self.pending_messages.append((messages, client_ids))


def make_empty_board():
    return [[GameBoardTypes.Nothing.value for _y in range(9)] for _x in range(12)]


def test_game_board_defaults_to_all_nothing_cells():
    game_board = server.GameBoard(RecordingGame())

    assert len(game_board.x_to_y_to_board_type) == 12
    assert all(len(column) == 9 for column in game_board.x_to_y_to_board_type)
    assert game_board.board_type_to_coordinates[GameBoardTypes.Nothing.value] == {
        (x, y) for x in range(12) for y in range(9)
    }


def test_set_cell_updates_indexes_and_emits_message():
    game = RecordingGame()
    game_board = server.GameBoard(game)

    game_board.set_cell((3, 4), GameBoardTypes.Luxor.value)

    assert game_board.x_to_y_to_board_type[3][4] == GameBoardTypes.Luxor.value
    assert (3, 4) not in game_board.board_type_to_coordinates[GameBoardTypes.Nothing.value]
    assert (3, 4) in game_board.board_type_to_coordinates[GameBoardTypes.Luxor.value]
    assert game.pending_messages == [
        (
            [[CommandsToClient.SetGameBoardCell.value, 3, 4, GameBoardTypes.Luxor.value]],
            {1, 2},
        )
    ]


def test_fill_cells_updates_connected_non_excluded_region():
    board = make_empty_board()
    board[1][1] = GameBoardTypes.NothingYet.value
    board[1][2] = GameBoardTypes.NothingYet.value
    board[2][1] = GameBoardTypes.NothingYet.value
    board[2][2] = GameBoardTypes.CantPlayEver.value
    board[3][1] = GameBoardTypes.NothingYet.value
    board[0][1] = GameBoardTypes.Luxor.value

    game = RecordingGame()
    game_board = server.GameBoard(game, board)

    game_board.fill_cells((1, 1), GameBoardTypes.Tower.value)

    assert game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.Tower.value
    assert game_board.x_to_y_to_board_type[1][2] == GameBoardTypes.Tower.value
    assert game_board.x_to_y_to_board_type[2][1] == GameBoardTypes.Tower.value
    assert game_board.x_to_y_to_board_type[2][2] == GameBoardTypes.CantPlayEver.value
    assert game_board.x_to_y_to_board_type[3][1] == GameBoardTypes.Tower.value
    assert game_board.x_to_y_to_board_type[0][1] == GameBoardTypes.Tower.value

    messages, client_ids = game.pending_messages[0]
    assert client_ids == {1, 2}
    assert messages == [
        [CommandsToClient.SetGameBoardCell.value, 1, 1, GameBoardTypes.Tower.value],
        [CommandsToClient.SetGameBoardCell.value, 0, 1, GameBoardTypes.Tower.value],
        [CommandsToClient.SetGameBoardCell.value, 2, 1, GameBoardTypes.Tower.value],
        [CommandsToClient.SetGameBoardCell.value, 1, 2, GameBoardTypes.Tower.value],
        [CommandsToClient.SetGameBoardCell.value, 3, 1, GameBoardTypes.Tower.value],
    ]


def test_fill_cells_does_not_cross_nothing_cells():
    board = make_empty_board()
    board[1][1] = GameBoardTypes.NothingYet.value
    board[3][1] = GameBoardTypes.NothingYet.value

    game = RecordingGame()
    game_board = server.GameBoard(game, board)

    game_board.fill_cells((1, 1), GameBoardTypes.Tower.value)

    assert game_board.x_to_y_to_board_type[1][1] == GameBoardTypes.Tower.value
    assert game_board.x_to_y_to_board_type[3][1] == GameBoardTypes.NothingYet.value
    assert game.pending_messages == [
        (
            [[CommandsToClient.SetGameBoardCell.value, 1, 1, GameBoardTypes.Tower.value]],
            {1, 2},
        )
    ]
