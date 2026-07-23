import io

import pytest
from enums import CommandsToClient

pytestmark = pytest.mark.unit


def run_chat_processor(logs_to_games, log_text, capsys):
    logs_to_games.ChatMessageProcessor(1700000000, io.StringIO(log_text)).go()
    return capsys.readouterr().out.splitlines()


def test_chat_message_processor_outputs_global_and_game_chat(
    logs_to_games_without_database,
    capsys,
):
    log_text = """
time: 1700000001.0
1 connect alice 127.0.0.1 socket-1 False
2 connect bob 127.0.0.2 socket-2 False
3 connect viewer 127.0.0.3 socket-3 False
1,2,3 <- [[8,99,0,1],[9,99,1,2],[12,99,3]]
time: 1700000002.5
1,2,3 <- [[21,1,"hello lobby"],[22,1,"hello table"],[22,2,"back again"],[22,3,"watching"]]
"""

    assert run_chat_processor(logs_to_games_without_database, log_text, capsys) == [
        "1700000002.5 GLOBAL alice -> hello lobby",
        "1700000002.5 GAME#99 alice -> hello table",
        "1700000002.5 GAME#99 bob -> back again",
        "1700000002.5 GAME#99 viewer -> watching",
    ]


def test_chat_message_processor_handles_legacy_game_player_client_id_command(
    logs_to_games_without_database,
    capsys,
):
    legacy_set_game_player_client_id = logs_to_games_without_database.Enums.lookups[
        "CommandsToClient"
    ].index("SetGamePlayerClientId")
    log_text = f"""
time: 1700000001.0
4 connect charlie 127.0.0.4 socket-4 False
4 <- [[{legacy_set_game_player_client_id},100,0,4]]
time: 1700000003.0
4 <- [[{CommandsToClient.AddGameChatMessage.value},4,"legacy mapping"]]
"""

    assert run_chat_processor(logs_to_games_without_database, log_text, capsys) == [
        "1700000003.0 GAME#100 charlie -> legacy mapping",
    ]


def test_chat_message_processor_ignores_legacy_null_client_id_mapping(
    logs_to_games_without_database,
    capsys,
):
    legacy_set_game_player_client_id = logs_to_games_without_database.Enums.lookups[
        "CommandsToClient"
    ].index("SetGamePlayerClientId")
    log_text = f"""
time: 1700000001.0
4 connect charlie 127.0.0.4 socket-4 False
4 <- [[{legacy_set_game_player_client_id},100,0,null]]
4 <- [[{CommandsToClient.AddGlobalChatMessage.value},4,"still global"]]
"""

    assert run_chat_processor(logs_to_games_without_database, log_text, capsys) == [
        "1700000001.0 GLOBAL charlie -> still global",
    ]


def test_chat_message_processor_continues_after_handler_errors(
    logs_to_games_without_database,
    capsys,
):
    processor = logs_to_games_without_database.ChatMessageProcessor(1700000000, io.StringIO(""))

    def raise_error(*_args):
        raise RuntimeError("chat handler failed")

    processor._commands_to_client_handlers[CommandsToClient.AddGlobalChatMessage.value] = (
        raise_error
    )

    processor._handle_command_to_client(
        [4],
        [[CommandsToClient.AddGlobalChatMessage.value, 4, "boom"]],
    )

    assert "RuntimeError: chat handler failed" in capsys.readouterr().err
