import types

import pytest

from acquire.enums import GameActions, GameBoardTypes, GameHistoryMessages

pytestmark = pytest.mark.unit


def make_empty_board(logs_to_games):
    return types.SimpleNamespace(
        x_to_y_to_board_type=[[GameBoardTypes.Nothing.value for _y in range(9)] for _x in range(12)]
    )


def test_tile_helpers_encode_coordinates(logs_to_games_without_database):
    assert logs_to_games_without_database.to_tile_string((0, 0)) == "1A"
    assert logs_to_games_without_database.to_tile_string((11, 8)) == "12I"
    assert logs_to_games_without_database.to_tile_int((0, 0)) == 0
    assert logs_to_games_without_database.to_tile_int((11, 8)) == 107


def test_game_board_lines_render_board_type_characters(logs_to_games_without_database):
    board = make_empty_board(logs_to_games_without_database)
    board.x_to_y_to_board_type[0][0] = GameBoardTypes.Luxor.value
    board.x_to_y_to_board_type[1][0] = GameBoardTypes.NothingYet.value
    board.x_to_y_to_board_type[2][0] = GameBoardTypes.CantPlayEver.value
    board.x_to_y_to_board_type[3][0] = GameBoardTypes.WillMergeChains.value

    lines = logs_to_games_without_database.get_game_board_lines(board)

    assert lines[0] == "LO\u2588m" + "\u00b7" * 8
    assert lines[1:] == ["\u00b7" * 12] * 8


def test_score_board_lines_mark_turn_and_move_players(logs_to_games_without_database):
    score_board = types.SimpleNamespace(
        player_data=[
            [1, 0, 0, 0, 0, 0, 0, 58, 61],
            [0, 2, 0, 0, 0, 0, 0, 45, 49],
        ],
        available=[24, 23, 25, 25, 25, 25, 25],
        chain_size=[2, 0, 11, 0, 0, 0, 0],
        price=[2, 0, 6, 0, 0, 0, 0],
    )

    lines = logs_to_games_without_database.get_score_board_lines(
        score_board,
        turn_player_id=0,
        move_player_id=1,
    )

    assert lines == [
        "P  L  T  A  F  W  C  I Cash  Net",
        "T  1                     58   61",
        "M     2                  45   49",
        "A 24 23 25 25 25 25 25",
        "C  2  - 11  -  -  -  -",
        "P  2  -  6  -  -  -  -",
    ]


def test_board_and_score_lines_are_combined_side_by_side(logs_to_games_without_database):
    lines = logs_to_games_without_database.get_game_board_lines_next_to_score_board_lines(
        ["board-one"],
        ["score-one", "score-two"],
    )

    assert lines == [
        "board-one  score-one",
        "              score-two",
    ]


def test_tile_rack_string_renders_tiles_and_empty_slots(logs_to_games_without_database):
    tiles = [
        [(0, 0), GameBoardTypes.Luxor.value],
        None,
        [(11, 8), GameBoardTypes.WillFormNewChain.value],
    ]

    assert logs_to_games_without_database.get_tile_rack_string(tiles) == "1A(L) none 12I(n)"


def test_parameter_strings_render_action_specific_inputs(logs_to_games_without_database):
    server_game = types.SimpleNamespace(
        tile_racks=types.SimpleNamespace(
            racks=[
                [
                    [(3, 4), GameBoardTypes.WillPutLonelyTileDown.value],
                ]
            ]
        )
    )

    assert logs_to_games_without_database.to_parameter_strings(
        server_game,
        0,
        GameActions.PlayTile,
        [0],
    ) == ["4E"]
    assert logs_to_games_without_database.to_parameter_strings(
        server_game,
        0,
        GameActions.SelectNewChain,
        [GameBoardTypes.Tower.value],
    ) == ["T"]
    assert logs_to_games_without_database.to_parameter_strings(
        server_game,
        0,
        GameActions.SelectMergerSurvivor,
        [GameBoardTypes.American.value],
    ) == ["A"]
    assert logs_to_games_without_database.to_parameter_strings(
        server_game,
        0,
        GameActions.SelectChainToDisposeOfNext,
        [GameBoardTypes.Festival.value],
    ) == ["F"]
    assert logs_to_games_without_database.to_parameter_strings(
        server_game,
        0,
        GameActions.DisposeOfShares,
        [2, 3],
    ) == ["2", "3"]
    assert logs_to_games_without_database.to_parameter_strings(
        server_game,
        0,
        GameActions.PurchaseShares,
        [[GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value], 1],
    ) == ["L,T", "1"]
    assert logs_to_games_without_database.to_parameter_strings(
        server_game,
        0,
        GameActions.PurchaseShares,
        [[], 0],
    ) == ["x", "0"]


def test_next_action_string_renders_action_prompts(logs_to_games_without_database):
    select_action = logs_to_games_without_database.server.ActionSelectNewChain.__new__(
        logs_to_games_without_database.server.ActionSelectNewChain
    )
    select_action.player_id = 1
    select_action.game_action_id = GameActions.SelectNewChain.value
    select_action.additional_params = [[GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value]]
    dispose_action = logs_to_games_without_database.server.ActionDisposeOfShares.__new__(
        logs_to_games_without_database.server.ActionDisposeOfShares
    )
    dispose_action.player_id = 0
    dispose_action.game_action_id = GameActions.DisposeOfShares.value
    dispose_action.additional_params = [
        GameBoardTypes.American.value,
        GameBoardTypes.Luxor.value,
    ]

    assert (
        logs_to_games_without_database.get_next_action_string(select_action)
        == "1 SelectNewChain L,T"
    )
    assert (
        logs_to_games_without_database.get_next_action_string(dispose_action)
        == "0 DisposeOfShares A"
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ([GameHistoryMessages.TurnBegan.value, 0], "0 TurnBegan"),
        ([GameHistoryMessages.StartedGame.value, 1], "1 StartedGame"),
        ([GameHistoryMessages.DrewTile.value, 0, 4, 5], "0 DrewTile 5F"),
        ([GameHistoryMessages.HasNoPlayableTile.value, 1], "1 HasNoPlayableTile"),
        ([GameHistoryMessages.PlayedTile.value, 1, 3, 4], "1 PlayedTile 4E"),
        ([GameHistoryMessages.FormedChain.value, 0, GameBoardTypes.Luxor.value], "0 FormedChain L"),
        (
            [
                GameHistoryMessages.MergedChains.value,
                0,
                [GameBoardTypes.Luxor.value, GameBoardTypes.Tower.value],
            ],
            "0 MergedChains L,T",
        ),
        (
            [
                GameHistoryMessages.SelectedMergerSurvivor.value,
                1,
                GameBoardTypes.American.value,
            ],
            "1 SelectedMergerSurvivor A",
        ),
        (
            [
                GameHistoryMessages.SelectedChainToDisposeOfNext.value,
                0,
                GameBoardTypes.Festival.value,
            ],
            "0 SelectedChainToDisposeOfNext F",
        ),
        (
            [
                GameHistoryMessages.ReceivedBonus.value,
                0,
                GameBoardTypes.Tower.value,
                3000,
            ],
            "0 ReceivedBonus T 3000",
        ),
        (
            [
                GameHistoryMessages.DisposedOfShares.value,
                1,
                GameBoardTypes.Luxor.value,
                2,
                1,
            ],
            "1 DisposedOfShares L 2 1",
        ),
        (
            [
                GameHistoryMessages.CouldNotAffordAnyShares.value,
                0,
            ],
            "0 CouldNotAffordAnyShares",
        ),
        (
            [
                GameHistoryMessages.PurchasedShares.value,
                1,
                [[GameBoardTypes.Luxor.value, 2], [GameBoardTypes.Tower.value, 1]],
            ],
            "1 PurchasedShares 2L,1T",
        ),
        (
            [GameHistoryMessages.PurchasedShares.value, 0, []],
            "0 PurchasedShares x",
        ),
        ([GameHistoryMessages.DrewLastTile.value, 1], "1 DrewLastTile"),
        (
            [GameHistoryMessages.ReplacedDeadTile.value, 0, 10, 8],
            "0 ReplacedDeadTile 11I",
        ),
        ([GameHistoryMessages.EndedGame.value, 1], "1 EndedGame"),
        (
            [GameHistoryMessages.NoTilesPlayedForEntireRound.value, None],
            "NoTilesPlayedForEntireRound",
        ),
        ([GameHistoryMessages.AllTilesPlayed.value, None], "AllTilesPlayed"),
    ],
)
def test_game_history_message_strings(logs_to_games_without_database, message, expected):
    assert (
        logs_to_games_without_database.get_game_history_message_string(
            {"alice": 0},
            message,
        )
        == expected
    )


def test_game_history_message_string_translates_username(logs_to_games_without_database):
    assert (
        logs_to_games_without_database.get_game_history_message_string(
            {"alice": 0},
            [GameHistoryMessages.DrewPositionTile.value, "alice", 3, 4],
        )
        == "0 DrewPositionTile 4E"
    )
