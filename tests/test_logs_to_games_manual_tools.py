import io
import pickle
import types
from pathlib import Path

import pytest

from acquire.enums import GameActions, GameBoardTypes, GameHistoryMessages

pytestmark = pytest.mark.unit


class FakeLogContext(io.StringIO):
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class FakeLogProcessor:
    games = []
    calls = []

    def __init__(self, log_timestamp, file, verbose=False, verbose_output_path=None):
        self.log_timestamp = log_timestamp
        self.file = file
        self.verbose = verbose
        self.verbose_output_path = verbose_output_path
        FakeLogProcessor.calls.append((log_timestamp, verbose, verbose_output_path))

    def go(self):
        yield from FakeLogProcessor.games


class FakeIndividualGameLogMaker:
    logs = []

    def __init__(self, log_timestamp, file):
        self.log_timestamp = log_timestamp
        self.file = file

    def go(self):
        yield from FakeIndividualGameLogMaker.logs


class FakeIndividualGameLog:
    def __init__(self, log_timestamp=1700000000, internal_game_id=77):
        self.log_timestamp = log_timestamp
        self.internal_game_id = internal_game_id
        self.written_filenames = []

    def make_game_log_file(self, filename):
        self.written_filenames.append(str(filename))
        with open(filename, "w") as file:
            file.write("game log\n")


def install_fake_log_inputs(monkeypatch, logs_to_games, filenames):
    monkeypatch.setattr(
        logs_to_games.util,
        "get_log_file_filenames",
        lambda *args, **kwargs: filenames,
    )
    monkeypatch.setattr(
        logs_to_games.util,
        "open_possibly_gzipped_file",
        lambda filename: FakeLogContext("log\n"),
    )


def make_replay_game(
    logs_to_games,
    *,
    internal_game_id=77,
    synchronized=True,
    state="InProgress",
    expired=True,
):
    game = types.SimpleNamespace(
        log_timestamp=1700000000,
        internal_game_id=internal_game_id,
        game_id=7,
        mode="Singles",
        max_players=2,
        state=state,
        expired=expired,
        played_tiles_order=[(0, 0), (1, 1)],
        player_id_to_username={0: "alice", 1: "bob"},
        username_to_player_id={"alice": 0, "bob": 1},
        player_join_order=["alice", "bob"],
        score=[90, 70],
        username_to_game_history={
            "alice": [
                [
                    logs_to_games.enums.GameHistoryMessages.ReceivedBonus.value,
                    0,
                    GameBoardTypes.Luxor.value,
                    3000,
                ],
                [logs_to_games.enums.GameHistoryMessages.PlayedTile.value, 0, 1, 1],
            ]
        },
        actions=[],
        is_server_game_synchronized=synchronized,
        sync_log=None if synchronized else ["sync", "diff"],
        made_server_game=False,
        written_server_game_files=[],
    )

    def make_server_game():
        game.made_server_game = True

    def compare_with_server_game():
        return None

    def make_server_game_file(filename):
        game.written_server_game_files.append(str(filename))
        with open(filename, "wb") as file:
            pickle.dump({"internal_game_id": internal_game_id}, file)

    def get_initial_tile_bag():
        return [(0, 0), (1, 1), (2, 2)]

    game.make_server_game = make_server_game
    game.compare_with_server_game = compare_with_server_game
    game.make_server_game_file = make_server_game_file
    game._get_initial_tile_bag = get_initial_tile_bag
    return game


def test_individual_game_log_round_trip_tool_writes_stage_files(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    output_dir = tmp_path
    (output_dir / "1").mkdir()
    (output_dir / "2").mkdir()
    game = make_replay_game(logs_to_games, internal_game_id=77)
    individual_game_log = FakeIndividualGameLog(internal_game_id=77)
    FakeLogProcessor.games = [game]
    FakeIndividualGameLogMaker.logs = [individual_game_log]
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1432798259, "server.log")])
    monkeypatch.setattr(logs_to_games, "LogProcessor", FakeLogProcessor)
    monkeypatch.setattr(logs_to_games, "IndividualGameLogMaker", FakeIndividualGameLogMaker)

    logs_to_games.test_individual_game_log(output_dir)

    assert (output_dir / "1" / "1700000000_00077.json").exists()
    assert (output_dir / "2" / "1700000000_00077.json").exists()
    assert individual_game_log.written_filenames == [str(output_dir / "1700000000_00077.txt")]
    assert capsys.readouterr().out.splitlines() == [
        "stage1 77",
        "stage2 77",
        "stage3 77",
    ]


def test_sync_log_tools_generate_and_report_outputs(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    unsynchronized = make_replay_game(logs_to_games, internal_game_id=77, synchronized=False)
    synchronized = make_replay_game(logs_to_games, internal_game_id=78)
    FakeLogProcessor.games = [unsynchronized, synchronized]
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1700000000, "server.log")])
    monkeypatch.setattr(logs_to_games, "LogProcessor", FakeLogProcessor)

    logs_to_games.output_sync_logs_for_all_unsynchronized_games(output_dir)
    logs_to_games.report_on_sync_logs(output_dir)

    sync_file = output_dir / "1700000000_00077_002_sync_log.txt"
    assert sync_file.read_text() == "sync\ndiff\n"
    output = capsys.readouterr().out
    assert "server.log" in output
    assert "1700000000 77 boo!" in output
    assert "1700000000 78 yay!" in output
    assert "without fully unknown tile racks:" in output


def test_make_individual_game_logs_for_each_sync_log_extracts_matching_games(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    input_dir = tmp_path / "sync"
    output_dir = tmp_path / "logs"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "1700000000_00077_002_sync_log.txt").write_text("diff\n")
    matching_log = FakeIndividualGameLog(internal_game_id=77)
    skipped_log = FakeIndividualGameLog(internal_game_id=78)
    FakeIndividualGameLogMaker.logs = [matching_log, skipped_log]
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1700000000, "server.log")])
    monkeypatch.setattr(logs_to_games, "IndividualGameLogMaker", FakeIndividualGameLogMaker)

    logs_to_games.make_individual_game_logs_for_each_sync_log(input_dir, output_dir)

    assert matching_log.written_filenames == [str(output_dir / "1700000000_00077.txt")]
    assert skipped_log.written_filenames == []
    assert "server.log" in capsys.readouterr().out


def test_tile_bag_tweak_tools_delegate_to_sync_and_verbose_comparison(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    calls = []
    monkeypatch.setattr(
        logs_to_games.Game,
        "tile_bag_tweaks",
        {(2, 20): [], (1, 10): []},
    )
    monkeypatch.setattr(
        logs_to_games,
        "_generate_sync_logs",
        lambda log_timestamp, filename, output_dir: calls.append(
            (log_timestamp, filename, str(output_dir))
        ),
    )

    logs_to_games.run_all_game_logs_with_tile_bag_tweaks(tmp_path / "in", tmp_path / "out")

    assert calls == [
        (1, str(tmp_path / "in" / "1_00010.txt"), str(tmp_path / "out")),
        (2, str(tmp_path / "in" / "2_00020.txt"), str(tmp_path / "out")),
    ]

    verbose_calls = []
    monkeypatch.setattr(
        logs_to_games,
        "verbosely_compare_individual_game_log",
        lambda *args: verbose_calls.append(args),
    )
    logs_to_games.verbosely_compare_individual_game_logs_with_tile_bag_tweaks(
        tmp_path / "in", tmp_path
    )

    assert verbose_calls == [
        (1, 10, tmp_path / "in", tmp_path),
        (2, 20, tmp_path / "in", tmp_path),
    ]
    assert (tmp_path / "1_00010_verbose_comparison.txt").exists()
    assert "1_00010_verbose_comparison.txt" in capsys.readouterr().out


def test_verbose_compare_outputs_sync_details(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    unsynchronized = make_replay_game(logs_to_games, internal_game_id=77, synchronized=False)
    synchronized = make_replay_game(logs_to_games, internal_game_id=78)
    FakeLogProcessor.games = [unsynchronized, synchronized]
    install_fake_log_inputs(monkeypatch, logs_to_games, [])
    monkeypatch.setattr(logs_to_games, "LogProcessor", FakeLogProcessor)

    logs_to_games.verbosely_compare_individual_game_log(1700000000, 77, tmp_path, tmp_path / "out")

    output = capsys.readouterr().out
    assert "sync_log:\nsync\ndiff" in output
    assert "1700000000 77 boo!" in output
    assert "1700000000 78 yay!" in output
    assert FakeLogProcessor.calls[-1] == (1700000000, True, tmp_path / "out")


def test_server_game_file_tools_write_expected_snapshots(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    old_game = make_replay_game(logs_to_games, internal_game_id=77, expired=True)
    recent_game = make_replay_game(logs_to_games, internal_game_id=78, expired=False)
    targeted_game = make_replay_game(logs_to_games, internal_game_id=79, expired=True)
    FakeLogProcessor.games = [old_game, recent_game, targeted_game]
    install_fake_log_inputs(
        monkeypatch,
        logs_to_games,
        [(1700000000, "old.log"), (1700000001, "recent.log")],
    )
    monkeypatch.setattr(logs_to_games, "LogProcessor", FakeLogProcessor)

    logs_to_games.output_server_game_files_for_all_in_progress_games(tmp_path)
    logs_to_games.output_server_game_file_for_game(1700000000, 79, tmp_path)

    assert (tmp_path / "1700000000_00077_002.bin").exists()
    assert (tmp_path / "1700000000_00079_002.bin").exists()
    assert old_game.made_server_game is True
    assert targeted_game.made_server_game is True
    assert "1700000000_00077_002.bin" in capsys.readouterr().out


def test_first_merge_bonus_export_writes_pickle(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
):
    logs_to_games = logs_to_games_without_database
    game = make_replay_game(logs_to_games, state="Completed")
    FakeLogProcessor.games = [game]
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1700000000, "server.log")])
    monkeypatch.setattr(logs_to_games, "LogProcessor", FakeLogProcessor)

    logs_to_games.output_first_merge_bonuses_and_final_scores_of_all_completed_games(tmp_path)

    with (tmp_path / "first_merge_bonuses_and_final_scores_of_all_completed_games.bin").open(
        "rb"
    ) as file:
        data = pickle.load(file)
    assert data == {"Singles2": [({GameBoardTypes.Luxor.value: {0: 3000}}, [90, 70])]}


def test_make_individual_game_log_writes_only_requested_game(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    matching_log = FakeIndividualGameLog(internal_game_id=77)
    skipped_log = FakeIndividualGameLog(internal_game_id=78)
    FakeIndividualGameLogMaker.logs = [skipped_log, matching_log]
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1700000000, "server.log")])
    monkeypatch.setattr(logs_to_games, "IndividualGameLogMaker", FakeIndividualGameLogMaker)

    logs_to_games.make_individual_game_log(1700000000, 77, tmp_path)

    assert matching_log.written_filenames == [str(tmp_path / "1700000000_00077.txt")]
    assert skipped_log.written_filenames == []
    assert "1700000000 77" in capsys.readouterr().out


def test_make_individual_game_log_exhausts_logs_when_game_is_not_found(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    skipped_log = FakeIndividualGameLog(internal_game_id=78)
    FakeIndividualGameLogMaker.logs = [skipped_log]
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1700000000, "server.log")])
    monkeypatch.setattr(logs_to_games, "IndividualGameLogMaker", FakeIndividualGameLogMaker)

    logs_to_games.make_individual_game_log(1700000000, 77, tmp_path)

    assert skipped_log.written_filenames == []
    assert capsys.readouterr().out == ""


def test_chat_and_username_database_tools_print_expected_output(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1700000000, "server.log")])

    class FakeChatMessageProcessor:
        def __init__(self, log_timestamp, file):
            self.log_timestamp = log_timestamp

        def go(self):
            print(self.log_timestamp, "GLOBAL alice -> hello")

    class FakeSession:
        class Bind:
            class Dialect:
                name = "postgresql"

            dialect = Dialect()

        def __init__(self):
            self.queries = []

        def get_bind(self):
            return self.Bind()

        def execute(self, query, params=None):
            self.queries.append(query)
            if params:
                return [types.SimpleNamespace(player_id=0, username="Alicia")]
            return [
                types.SimpleNamespace(user_id=1, name="José"),
                types.SimpleNamespace(user_id=2, name="O'José"),
                types.SimpleNamespace(user_id=3, name=b"Alice"),
            ]

    class FakeSessionScope:
        session = FakeSession()

        def __enter__(self):
            return self.session

        def __exit__(self, exc_type, exc_value, traceback):
            return None

    fake_session_scope = FakeSessionScope()
    game = make_replay_game(logs_to_games)
    game.player_id_to_username = {0: "alice"}
    FakeLogProcessor.games = [game]
    monkeypatch.setattr(logs_to_games, "ChatMessageProcessor", FakeChatMessageProcessor)
    monkeypatch.setattr(logs_to_games, "LogProcessor", FakeLogProcessor)
    monkeypatch.setattr(
        logs_to_games.orm,
        "session_scope",
        lambda: fake_session_scope,
        raising=False,
    )

    logs_to_games.output_chat_messages(1700000000)
    logs_to_games.compare_log_usernames_with_database_usernames(1700000000)
    logs_to_games.punycode_non_ascii_usernames_in_the_database()

    output = capsys.readouterr().out
    assert "1700000000 GLOBAL alice -> hello" in output
    assert '[1700000000,77,"alice","Alicia"]' in output
    assert 'update "user" set name = \'Jos-dma\' where user_id = 1;' in output
    assert 'update "user" set name = \'O\'\'Jos-fsa\' where user_id = 2;' in output
    assert all('"user"' in query for query in fake_session_scope.session.queries)
    assert logs_to_games.sql_string_literal("A\\Jos-fsa") == "'A\\Jos-fsa'"


def test_log_file_size_and_username_id_tools_print_generated_data(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
    capsys,
):
    logs_to_games = logs_to_games_without_database
    plain = tmp_path / "plain.log"
    gzipped = tmp_path / "compressed.log.gz"
    plain.write_text("x" * 100)
    gzipped.write_text("x" * 10)
    monkeypatch.setattr(
        logs_to_games.util,
        "get_log_file_filenames",
        lambda *args, **kwargs: [(200, str(plain)), (300, str(gzipped))],
    )

    logs_to_games.output_log_file_filenames_in_reverse_size_order()

    class FakeLogParser:
        def __init__(self, log_timestamp, file):
            self.log_timestamp = log_timestamp

        def go(self):
            yield logs_to_games.LineTypes.connect, 1, "", [1, "José"]
            yield logs_to_games.LineTypes.connect, 2, "", [2, "Temp"]

    username_file = io.StringIO(
        "username_to_user_id = {\n"
        "    # log_timestamp: 100\n"
        "    'alice': 1,\n"
        "    # log_timestamp: 200\n"
    )
    opened_username_paths = []

    def open_username_mapping(filename):
        opened_username_paths.append(Path(filename).resolve())
        return username_file

    monkeypatch.setattr(logs_to_games, "open", open_username_mapping, raising=False)
    monkeypatch.setattr(logs_to_games, "LogParser", FakeLogParser)
    monkeypatch.setattr(logs_to_games, "username_to_user_id", {"alice": 1})
    monkeypatch.setattr(
        logs_to_games.util,
        "open_possibly_gzipped_file",
        lambda filename: FakeLogContext("log\n"),
    )

    logs_to_games.output_username_to_user_id()

    output = capsys.readouterr().out
    assert output.splitlines()[:2] == ["200", "300"]
    assert "    'Jos-dma': 2, # original non-ascii: José" in output
    assert "    'Temp': 3," in output
    assert opened_username_paths == [
        Path(logs_to_games.username_to_user_id_module.__file__).resolve()
    ]
    assert "src/acquire/username_to_user_id.py" in opened_username_paths[0].as_posix()


def test_make_acquire2_game_test_files_writes_replay_text(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
):
    logs_to_games = logs_to_games_without_database
    game = make_replay_game(logs_to_games, state="Completed")
    game.actions = [
        [0, [GameActions.PurchaseShares.value, [], 0], 12.345],
        [0, [GameActions.PlayTile.value, 0], 13.0],
    ]
    FakeLogProcessor.games = [game]
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1700000000, "server.log")])
    monkeypatch.setattr(logs_to_games, "LogProcessor", FakeLogProcessor)
    monkeypatch.setattr(
        logs_to_games,
        "username_to_user_id",
        {"alice": 101, "bob": 102},
    )

    class FakeScoreSheet:
        username_to_player_id = {"alice": 0, "bob": 1}
        player_data = [[0, 0, 0, 0, 0, 0, 0, 60, 60], [0, 0, 0, 0, 0, 0, 0, 60, 60]]
        available = [25] * 7
        chain_size = [0] * 7
        price = [0] * 7

        def update_net_worths(self):
            return None

    class FakeServerGame:
        def __init__(self, *args):
            self.score_sheet = FakeScoreSheet()
            self.game_board = types.SimpleNamespace(
                x_to_y_to_board_type=[
                    [GameBoardTypes.Nothing.value for _y in range(9)] for _x in range(12)
                ]
            )
            self.tile_racks = types.SimpleNamespace(
                racks=[[[((0, 0)), GameBoardTypes.WillPutLonelyTileDown.value]], []]
            )
            self.turn_player_id = 0
            self.history_messages = []
            self.actions = [
                types.SimpleNamespace(
                    player_id=0,
                    game_action_id=GameActions.PurchaseShares.value,
                    additional_params=[],
                )
            ]

        def join_game(self, client):
            return None

        def do_game_action(self, client, game_action_id, data):
            self.history_messages.append([None, [GameHistoryMessages.AllTilesPlayed.value, None]])
            self.actions = [
                types.SimpleNamespace(
                    player_id=0,
                    game_action_id=game_action_id,
                    additional_params=[],
                )
            ]

    monkeypatch.setattr(logs_to_games.server, "Game", FakeServerGame)

    logs_to_games.make_acquire2_game_test_files(1700000000, tmp_path)

    output_file = tmp_path / "1700000000" / "000077_002.txt"
    text = output_file.read_text()
    assert "game mode: SINGLES_2" in text
    assert "user: 101 alice" in text
    assert "timestamp: 12345" in text
    assert "action: 0 PurchaseShares x 0" in text
    assert "history messages:" in text


def test_make_acquire2_game_test_files_continues_after_action_errors(
    logs_to_games_without_database,
    monkeypatch,
    tmp_path,
):
    logs_to_games = logs_to_games_without_database
    game = make_replay_game(logs_to_games, state="Completed")
    game.actions = [
        [0, [GameActions.PurchaseShares.value, [], 0], 12.345],
        [0, [GameActions.PlayTile.value, 0], 13.0],
    ]
    FakeLogProcessor.games = [game]
    install_fake_log_inputs(monkeypatch, logs_to_games, [(1700000000, "server.log")])
    monkeypatch.setattr(logs_to_games, "LogProcessor", FakeLogProcessor)
    monkeypatch.setattr(logs_to_games, "username_to_user_id", {"alice": 101, "bob": 102})

    calls = []

    def fake_to_parameter_strings(*_args):
        calls.append("parameters")
        if len(calls) == 1:
            raise RuntimeError("parameters failed")
        return ["x 0"]

    class FakeScoreSheet:
        username_to_player_id = {"alice": 0, "bob": 1}
        player_data = [[0, 0, 0, 0, 0, 0, 0, 60, 60], [0, 0, 0, 0, 0, 0, 0, 60, 60]]
        available = [25] * 7
        chain_size = [0] * 7
        price = [0] * 7

        def update_net_worths(self):
            return None

    class FakeServerGame:
        def __init__(self, *args):
            self.score_sheet = FakeScoreSheet()
            self.game_board = types.SimpleNamespace(
                x_to_y_to_board_type=[
                    [GameBoardTypes.Nothing.value for _y in range(9)] for _x in range(12)
                ]
            )
            self.tile_racks = types.SimpleNamespace(racks=[[], []])
            self.turn_player_id = 0
            self.history_messages = []
            self.actions = [
                types.SimpleNamespace(
                    player_id=0,
                    game_action_id=GameActions.PlayTile.value,
                    additional_params=[],
                )
            ]

        def join_game(self, client):
            return None

        def do_game_action(self, client, game_action_id, data):
            raise RuntimeError("action failed")

    monkeypatch.setattr(logs_to_games, "to_parameter_strings", fake_to_parameter_strings)
    monkeypatch.setattr(logs_to_games.server, "Game", FakeServerGame)

    logs_to_games.make_acquire2_game_test_files(1700000000, tmp_path)

    assert calls == ["parameters", "parameters"]
