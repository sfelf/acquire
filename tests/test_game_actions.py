import pytest
import server
from enums import CommandsToClient, GameActions, GameBoardTypes, GameHistoryMessages


pytestmark = pytest.mark.unit


class RecordingGame:
    def __init__(self, board=None):
        self.num_players = 2
        self.client_ids = {10, 11}
        self.pending_messages = []
        self.history_messages = []
        self.turn_player_id = None
        self.turns_without_played_tiles_count = 0
        self.game_board = server.GameBoard(self, board)
        self.score_sheet = server.ScoreSheet(self)
        self.score_sheet.player_data = [
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "player_0", None, None],
            [0, 0, 0, 0, 0, 0, 0, 60, 60, "player_1", None, None],
        ]
        self.tile_racks = RecordingTileRacks()

    def add_pending_messages(self, messages, client_ids=None):
        self.pending_messages.append((messages, client_ids))

    def add_history_message(self, *args, **kwargs):
        self.history_messages.append((args, kwargs))


class RecordingTileRacks:
    def __init__(self, racks=None):
        self.racks = racks if racks is not None else [[None] * 6, [None] * 6]
        self.removed_tiles = []
        self.determine_calls = []

    def remove_tile(self, player_id, tile_index):
        self.removed_tiles.append((player_id, tile_index))
        self.racks[player_id][tile_index] = None

    def determine_tile_game_board_types(self, player_ids=None):
        self.determine_calls.append(player_ids)


def make_empty_board():
    return [
        [GameBoardTypes.Nothing.value for _y in range(9)]
        for _x in range(12)
    ]


def test_action_send_message_includes_action_and_player_ids():
    game = RecordingGame()
    action = server.ActionPlayTile(game, 1)

    action.send_message({11})

    assert game.pending_messages == [
        ([[CommandsToClient.SetGameAction.value, GameActions.PlayTile.value, 1]], {11})
    ]


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
    assert game.pending_messages == [
        ([[CommandsToClient.SetTurn.value, 0]], {10, 11})
    ]
    assert game.history_messages == [
        ((GameHistoryMessages.TurnBegan.value, 0), {})
    ]


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
    assert game.history_messages == [
        ((GameHistoryMessages.PlayedTile.value, 0, 1, 1), {})
    ]


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
    assert game.history_messages == [
        ((GameHistoryMessages.PlayedTile.value, 0, 1, 1), {})
    ]


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
    assert game.history_messages == [
        ((GameHistoryMessages.PlayedTile.value, 0, 1, 1), {})
    ]


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
