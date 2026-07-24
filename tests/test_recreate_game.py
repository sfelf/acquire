import importlib
import pickle
import sys
import types

import pytest

import acquire
from acquire import game_server as server
from acquire.enums import GameActions, GameBoardTypes, GameModes, GameStates

pytestmark = pytest.mark.unit


class SessionScope:
    def __init__(self, rows):
        self.rows = rows
        self.query_args = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def query(self, *args):
        self.query_args = args
        return self

    def all(self):
        return self.rows


@pytest.fixture
def recreate_game_without_database(monkeypatch):
    monkeypatch.delitem(sys.modules, "acquire.recreate_game", raising=False)

    orm = types.ModuleType("acquire.orm")
    orm.Game = types.SimpleNamespace(log_time="log_time_column", number="number_column")
    orm.rows = []
    orm.session = None

    def session_scope():
        orm.session = SessionScope(orm.rows)
        return orm.session

    orm.session_scope = session_scope
    monkeypatch.setitem(sys.modules, "acquire.orm", orm)
    monkeypatch.setattr(acquire, "orm", orm, raising=False)

    try:
        yield importlib.import_module("acquire.recreate_game")
    finally:
        sys.modules.pop("acquire.recreate_game", None)


def make_saved_game_data(tile_racks=None):
    return {
        "state": GameStates.InProgress.value,
        "mode": GameModes.Singles.value,
        "max_players": 3,
        "num_players": 2,
        "tile_bag": [(0, 0), (1, 1)],
        "turn_player_id": 1,
        "turns_without_played_tiles_count": 2,
        "history_messages": [[None, [1, "alice", 3, 4]]],
        "game_board": [[GameBoardTypes.Nothing.value for _y in range(9)] for _x in range(12)],
        "score_sheet": {
            "player_data": [
                [1, 0, 0, 0, 0, 0, 0, 58, 61, "alice", None, None],
                [0, 2, 0, 0, 0, 0, 0, 45, 49, "bob", None, None],
            ],
            "available": [24, 23, 25, 25, 25, 25, 25],
            "chain_size": [2, 3, 0, 0, 0, 0, 0],
            "price": [2, 3, 0, 0, 0, 0, 0],
            "creator_username": "alice",
            "username_to_player_id": {"alice": 0, "bob": 1},
        },
        "tile_racks": tile_racks,
        "actions": [
            {
                "__name__": "ActionPlayTile",
                "player_id": 1,
                "game_action_id": GameActions.PlayTile.value,
                "additional_params": ["kept"],
            }
        ],
        "log_time": 1700000000,
        "internal_game_id": 12,
        "game_id": 99,
        "begin": 1700000100,
    }


def test_recreate_game_restores_saved_state_from_pickle(
    recreate_game_without_database,
    tmp_path,
):
    saved_data = make_saved_game_data(
        tile_racks=[
            [[(3, 4), GameBoardTypes.WillPutLonelyTileDown.value, False], None],
            [None],
        ]
    )
    saved_data["game_board"][3][4] = GameBoardTypes.NothingYet.value
    filename = tmp_path / "game.bin"
    with filename.open("wb") as file:
        pickle.dump(saved_data, file)
    game_server = server.Server()

    recreate_game_without_database.recreate_game(game_server, filename)

    game = game_server.game_id_to_game[1]
    assert game.game_id == 1
    assert game.internal_game_id == 1
    assert game.state == GameStates.InProgress.value
    assert game.mode == GameModes.Singles.value
    assert game.max_players == 3
    assert game.num_players == 2
    assert game.tile_bag == [(0, 0), (1, 1)]
    assert game.turn_player_id == 1
    assert game.turns_without_played_tiles_count == 2
    assert game.history_messages == [[None, [1, "alice", 3, 4]]]
    assert game.add_pending_messages == game_server.add_pending_messages
    assert game.logging_enabled is True
    assert game.client_ids == set()
    assert game.watcher_client_ids == set()
    assert game.expiration_time is None
    assert game.game_board.x_to_y_to_board_type[3][4] == GameBoardTypes.NothingYet.value
    assert game.score_sheet.game is game
    assert game.score_sheet.player_data == saved_data["score_sheet"]["player_data"]
    assert game.tile_racks.game is game
    assert game.tile_racks.racks == saved_data["tile_racks"]
    assert len(game.actions) == 1
    assert isinstance(game.actions[0], server.ActionPlayTile)
    assert game.actions[0].game is game
    assert game.actions[0].player_id == 1
    assert game.actions[0].additional_params == ["kept"]
    assert game.log_data_overrides == {
        "log-time": 1700000000,
        "game-id": 12,
        "external-game-id": 99,
        "end": 1700001900,
    }


def test_recreate_game_restores_missing_tile_racks_as_none(
    recreate_game_without_database,
    tmp_path,
):
    filename = tmp_path / "game.bin"
    with filename.open("wb") as file:
        pickle.dump(make_saved_game_data(tile_racks=None), file)
    game_server = server.Server()

    recreate_game_without_database.recreate_game(game_server, filename)

    assert game_server.game_id_to_game[1].tile_racks is None


def test_recreate_some_games_recreates_top_five_unrecreated_snapshots(
    recreate_game_without_database,
    monkeypatch,
):
    recreated_filenames = []
    game_server = server.Server()
    recreate_game_without_database.orm.rows = [
        types.SimpleNamespace(log_time=1700000000, number=3),
    ]
    monkeypatch.setattr(
        recreate_game_without_database.os,
        "listdir",
        lambda _input_dir: [
            "1700000000_00003_010.bin",
            "1700000000_00004_020.bin",
            "1700000001_00005_015.bin",
            "1700000002_00006_025.bin",
            "1700000003_00007_005.bin",
            "1700000004_00008_030.bin",
            "1700000005_00009_001.bin",
            "not-a-game.bin",
        ],
    )
    monkeypatch.setattr(
        recreate_game_without_database,
        "recreate_game",
        lambda _server, filename: recreated_filenames.append(filename),
    )

    recreate_game_without_database.recreate_some_games(game_server)

    assert recreate_game_without_database.orm.session.query_args == (
        "log_time_column",
        "number_column",
    )
    assert recreated_filenames == [
        "/opt/data/tim/1700000004_00008_030.bin",
        "/opt/data/tim/1700000002_00006_025.bin",
        "/opt/data/tim/1700000000_00004_020.bin",
        "/opt/data/tim/1700000001_00005_015.bin",
        "/opt/data/tim/1700000003_00007_005.bin",
    ]
