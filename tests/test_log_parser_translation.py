import io

import pytest

from acquire.enums import CommandsToClient, CommandsToServer, Errors

pytestmark = pytest.mark.unit


def parse_events(logs_to_games, log_text, log_timestamp=1700000000):
    return list(logs_to_games.LogParser(log_timestamp, io.StringIO(log_text)).go())


def event_summary(events):
    return [
        (line_type.name if line_type else None, line_number, data)
        for line_type, line_number, _line, data in events
    ]


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


def test_commands_to_client_translator_leaves_commands_without_translations(
    logs_to_games_without_database,
):
    translator = logs_to_games_without_database.CommandsToClientTranslator({})
    commands = [
        [CommandsToClient.FatalError.value, Errors.InvalidUsername.value],
        [CommandsToClient.SetGameWatcherClientId.value, 99, 3],
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

    events = parse_events(logs_to_games_without_database, log_text)

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

    events = parse_events(logs_to_games_without_database, log_text)

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

    events = parse_events(logs_to_games_without_database, log_text)

    assert [(event[0].name, event[1], event[3]) for event in events] == [
        ("blank_line", 1, ()),
        ("connection_made", 2, ()),
        ("time", 3, (1700000001.0,)),
        ("blank_line", 5, ()),
    ]


def test_log_parser_parses_supported_line_shapes(logs_to_games_without_database):
    log_text = """
time: 1700000001.25
7,8 <- [[1,"payload"]]
9 -> [5,1,["x"]]
{"_":"game","game-id":12}
42 connect alice 1.2.3.4 socket-1 True
43 disconnect
game #99 expired (internal #123)
44 connect 1.2.3.4 bob
999 -> 45 disconnect
999 connect 46 -> [5,2,["y"]]
connection_made
"""

    events = parse_events(logs_to_games_without_database, log_text)

    assert event_summary(events) == [
        ("blank_line", 1, ()),
        ("time", 2, (1700000001.25,)),
        (
            "command_to_client",
            3,
            ([7, 8], [[CommandsToClient.SetClientId.value, "payload"]]),
        ),
        (
            "command_to_server",
            4,
            (9, [CommandsToServer.DoGameAction.value, 1, ["x"]]),
        ),
        ("log", 5, ({"_": "game", "game-id": 12},)),
        ("connect", 6, (42, "alice")),
        ("disconnect", 7, (43,)),
        ("game_expired", 8, (99,)),
        ("connect", 9, (44, "bob")),
        ("disconnect", 10, (45,)),
        (
            "command_to_server",
            11,
            (46, [CommandsToServer.DoGameAction.value, 2, ["y"]]),
        ),
        ("connection_made", 12, ()),
        ("blank_line", 13, ()),
    ]


@pytest.mark.parametrize(
    "ignored_line",
    [
        " AttributeError stack detail",
        "AttributeError: thing broke",
        "connection_lost",
        "Exception in callback callback_name",
        "handle: <Handle thing>",
        "ImportError: missing module",
        "socket.send() raised exception.",
        "Traceback (most recent call last):",
        "UnicodeEncodeError: codec issue",
    ],
)
def test_log_parser_marks_ignored_error_lines_as_errors(
    logs_to_games_without_database,
    ignored_line,
):
    events = parse_events(logs_to_games_without_database, ignored_line)

    assert event_summary(events) == [
        ("error", 1, ()),
        ("blank_line", 2, ()),
    ]


@pytest.mark.parametrize(
    "log_text",
    [
        "1 <- not-json",
        "1 -> not-json",
        "{not-json",
        "this line has no parser",
    ],
)
def test_log_parser_yields_unhandled_event_for_malformed_lines(
    logs_to_games_without_database,
    log_text,
):
    events = parse_events(logs_to_games_without_database, log_text)

    assert event_summary(events) == [
        (None, 1, None),
        ("blank_line", 2, ()),
    ]


def test_log_parser_does_not_add_extra_blank_line_when_input_ends_blank(
    logs_to_games_without_database,
):
    events = parse_events(logs_to_games_without_database, "time: 1.0\n\n")

    assert event_summary(events) == [
        ("time", 1, (1.0,)),
        ("blank_line", 2, ()),
    ]
