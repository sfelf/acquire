import io

import pytest
from enums import CommandsToClient, Errors


pytestmark = pytest.mark.unit


def test_enums_return_legacy_translations_for_old_log_timestamps(
    logs_to_games_without_database,
):
    translations = logs_to_games_without_database.Enums.get_translations(1400000000)

    commands_translation = translations["CommandsToClient"]
    errors_translation = translations["Errors"]
    assert commands_translation[8] == logs_to_games_without_database.Enums.lookups[
        "CommandsToClient"
    ].index("SetGamePlayerUsername")
    assert commands_translation[9] == logs_to_games_without_database.Enums.lookups[
        "CommandsToClient"
    ].index("SetGamePlayerClientId")
    assert commands_translation[10] == CommandsToClient.SetGameWatcherClientId.value
    assert errors_translation[1] == Errors.InvalidUsername.value
    assert errors_translation[2] == Errors.UsernameAlreadyInUse.value


def test_enums_do_not_return_legacy_translations_for_modern_log_timestamps(
    logs_to_games_without_database,
):
    assert logs_to_games_without_database.Enums.get_translations(1700000000) == {}


def test_commands_to_client_translator_updates_legacy_command_and_error_indexes(
    logs_to_games_without_database,
):
    translations = logs_to_games_without_database.Enums.get_translations(1400000000)
    translator = logs_to_games_without_database.CommandsToClientTranslator(translations)
    commands = [
        [0, 1],
        [10, 99, 3],
    ]

    translator.translate(commands)

    assert commands == [
        [CommandsToClient.FatalError.value, Errors.InvalidUsername.value],
        [CommandsToClient.SetGameWatcherClientId.value, 99, 3],
    ]


def test_log_parser_reorders_game_player_commands_before_board_cells(
    logs_to_games_without_database,
):
    log_text = """
1 <- [[4,3,4,8],[8,99,0,1],[9,99,1,2],[16,0]]
"""

    events = list(
        logs_to_games_without_database.LogParser(
            1700000000,
            io.StringIO(log_text),
        ).go()
    )

    assert events[1][0] == logs_to_games_without_database.LineTypes.command_to_client
    assert events[1][3] == (
        [1],
        [
            [CommandsToClient.SetGamePlayerJoin.value, 99, 0, 1],
            [CommandsToClient.SetGamePlayerRejoin.value, 99, 1, 2],
            [CommandsToClient.SetGameBoardCell.value, 3, 4, 8],
            [CommandsToClient.SetTurn.value, 0],
        ],
    )


def test_log_parser_leaves_commands_in_original_order_without_board_cell(
    logs_to_games_without_database,
):
    log_text = """
1 <- [[16,0],[8,99,0,1]]
"""

    events = list(
        logs_to_games_without_database.LogParser(
            1700000000,
            io.StringIO(log_text),
        ).go()
    )

    assert events[1][3] == (
        [1],
        [
            [CommandsToClient.SetTurn.value, 0],
            [CommandsToClient.SetGamePlayerJoin.value, 99, 0, 1],
        ],
    )


def test_log_parser_stops_after_second_connection_made(
    logs_to_games_without_database,
):
    log_text = """
connection_made
time: 1700000001.0
connection_made
time: 1700000002.0
"""

    events = list(
        logs_to_games_without_database.LogParser(
            1700000000,
            io.StringIO(log_text),
        ).go()
    )

    assert [(event[0].name, event[1], event[3]) for event in events] == [
        ("blank_line", 1, ()),
        ("connection_made", 2, ()),
        ("time", 3, (1700000001.0,)),
        ("blank_line", 5, ()),
    ]
