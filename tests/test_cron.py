import contextlib
import importlib
import io
import sys
import types

import pytest
import ujson


pytestmark = pytest.mark.unit


class FakeRating:
    def __init__(self, user=None, rating_type=None, time=None, mu=None, sigma=None):
        self.user = user
        self.rating_type = rating_type
        self.time = time
        self.mu = mu
        self.sigma = sigma


class FakeRecord:
    def __init__(self, user=None, encoded=""):
        self.user = user
        self.encoded = encoded


@pytest.fixture
def cron_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "cron", raising=False)

    fake_orm = types.ModuleType("orm")
    fake_orm.Rating = FakeRating
    fake_orm.Record = FakeRecord
    fake_orm.Lookup = lambda session: None
    fake_orm.session_scope = contextlib.nullcontext
    monkeypatch.setitem(sys.modules, "orm", fake_orm)

    fake_sqlalchemy = types.ModuleType("sqlalchemy")
    fake_sqlalchemy.orm = types.ModuleType("sqlalchemy.orm")
    fake_sqlalchemy.sql = types.ModuleType("sqlalchemy.sql")
    fake_sqlalchemy.types = types.ModuleType("sqlalchemy.types")
    fake_sqlalchemy.sql.text = lambda query: query
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqlalchemy)
    monkeypatch.setitem(sys.modules, "sqlalchemy.orm", fake_sqlalchemy.orm)
    monkeypatch.setitem(sys.modules, "sqlalchemy.sql", fake_sqlalchemy.sql)
    monkeypatch.setitem(sys.modules, "sqlalchemy.types", fake_sqlalchemy.types)

    fake_trueskill = types.ModuleType("trueskill")
    fake_trueskill.MU = 25.0
    fake_trueskill.SIGMA = 8.333

    class Rating:
        def __init__(self, mu, sigma):
            self.mu = mu
            self.sigma = sigma

    class TrueSkill:
        def __init__(self, beta, draw_probability):
            self.beta = beta
            self.draw_probability = draw_probability

        def rate(self, rating_groups, ranks):
            return [
                [
                    Rating(rating.mu + index + 1, rating.sigma - 1)
                    for rating in rating_group
                ]
                for index, rating_group in enumerate(rating_groups)
            ]

    fake_trueskill.Rating = Rating
    fake_trueskill.TrueSkill = TrueSkill
    monkeypatch.setitem(sys.modules, "trueskill", fake_trueskill)

    try:
        yield importlib.import_module("cron")
    finally:
        sys.modules.pop("cron", None)


class FakeUser:
    def __init__(self, user_id, name):
        self.user_id = user_id
        self.name = name


class FakeGameMode:
    def __init__(self, name):
        self.name = name


class FakeGame:
    def __init__(self, log_time=123, game_id=456, mode="Singles"):
        self.log_time = log_time
        self.game_id = game_id
        self.begin_time = None
        self.end_time = None
        self.game_state = None
        self.game_mode = FakeGameMode(mode)


class FakeGamePlayer:
    def __init__(self, user, score=None):
        self.user = user
        self.score = score


class FakeSession:
    def __init__(self):
        self.added = []
        self.executions = []

    def add(self, item):
        self.added.append(item)

    def add_all(self, items):
        self.added.extend(items)

    def execute(self, sql, params=None):
        self.executions.append((sql, params))
        return []

    def flush(self):
        self.flushed = True


class FakeLookup:
    def __init__(self):
        self.games = {}
        self.game_players = {}
        self.users = {}
        self.ratings = {}
        self.added_ratings = []
        self.records = {}
        self.added_records = []
        self.key_values = {}

    def get_game(self, log_time, game_id):
        return self.games.setdefault((log_time, game_id), FakeGame(log_time, game_id))

    def get_game_state(self, name):
        return types.SimpleNamespace(name=name)

    def get_game_mode(self, name):
        return FakeGameMode(name)

    def get_game_player(self, game, player_index):
        key = (game.log_time, game.game_id, player_index)
        user = self.users.setdefault(
            "player%d" % player_index,
            FakeUser(player_index + 1, "player%d" % player_index),
        )
        return self.game_players.setdefault(key, FakeGamePlayer(user))

    def get_user(self, username):
        return self.users.setdefault(username, FakeUser(len(self.users) + 1, username))

    def get_rating_type(self, name):
        return types.SimpleNamespace(name=name)

    def get_rating(self, user, rating_type):
        return self.ratings.get((user.user_id, rating_type.name))

    def add_rating(self, rating):
        self.added_ratings.append(rating)
        self.ratings[(rating.user.user_id, rating.rating_type.name)] = rating

    def get_record(self, user):
        return self.records.get(user.user_id)

    def add_record(self, record):
        self.added_records.append(record)
        self.records[record.user.user_id] = record

    def get_key_value(self, name):
        return self.key_values.setdefault(name, types.SimpleNamespace(value=None))


def test_get_empty_records_returns_fresh_zero_buckets(cron_module):
    first = cron_module.get_empty_records()
    second = cron_module.get_empty_records()

    assert first == [
        [0, 0],
        [0, 0, 0],
        [0, 0, 0, 0],
        [0, 0],
    ]
    assert first is not second
    first[0][0] = 99
    assert second[0][0] == 0


def test_process_logs_dispatches_complete_json_lines(cron_module):
    logs2db = cron_module.Logs2DB(FakeSession(), FakeLookup())
    calls = []
    logs2db.method_lookup = {
        "game": lambda params: calls.append(("game", params)),
        "game-player": lambda params: calls.append(("game-player", params)),
    }
    file = io.StringIO(
        '{"_":"game","game-id":1}\n'
        '{"_":"ignored","game-id":1}\n'
        '{"_":"game-player","game-id":1}'
    )

    offset, completed_game_users = logs2db.process_logs(file, log_time=123)

    assert offset == len('{"_":"game","game-id":1}\n{"_":"ignored","game-id":1}\n')
    assert completed_game_users == set()
    assert calls == [
        ("game", {"_": "game", "game-id": 1, "log-time": 123}),
    ]


def test_process_game_updates_game_fields_and_delegates_scores(cron_module, monkeypatch):
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(FakeSession(), lookup)
    processed_results = []
    monkeypatch.setattr(logs2db, "process_game_result", processed_results.append)

    logs2db.process_game(
        {
            "log-time": 10,
            "game-id": 20,
            "begin": 100,
            "end": 200,
            "state": "Completed",
            "mode": "Singles",
            "score": [70, 60],
        }
    )

    game = lookup.get_game(10, 20)
    assert game.begin_time == 100
    assert game.end_time == 200
    assert game.game_state.name == "Completed"
    assert game.game_mode.name == "Singles"
    assert processed_results == [
        {
            "log-time": 10,
            "game-id": 20,
            "begin": 100,
            "end": 200,
            "state": "Completed",
            "mode": "Singles",
            "score": [70, 60],
            "scores": [70, 60],
        }
    ]


def test_process_game_player_assigns_user_to_player(cron_module):
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(FakeSession(), lookup)

    logs2db.process_game_player(
        {
            "log-time": 10,
            "game-id": 20,
            "player-id": 1,
            "username": "alice",
        }
    )

    game = lookup.get_game(10, 20)
    game_player = lookup.get_game_player(game, 1)
    assert game_player.user.name == "alice"


def test_process_game_result_updates_scores_and_completed_users(
    cron_module, monkeypatch
):
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(FakeSession(), lookup)
    logs2db.completed_game_users = set()
    calculated = []
    updated = []
    monkeypatch.setattr(logs2db, "calculate_new_ratings", lambda *args: calculated.append(args))
    monkeypatch.setattr(logs2db, "update_records", lambda *args: updated.append(args))

    logs2db.process_game_result({"log-time": 10, "game-id": 20, "scores": [70, 60]})

    game = lookup.get_game(10, 20)
    first_player = lookup.get_game_player(game, 0)
    second_player = lookup.get_game_player(game, 1)
    assert first_player.score == 70
    assert second_player.score == 60
    assert logs2db.completed_game_users == {first_player.user, second_player.user}
    assert calculated == [(game, [first_player, second_player])]
    assert updated == [(game, [first_player, second_player])]


def test_calculate_new_ratings_adds_initial_and_result_ratings(cron_module):
    session = FakeSession()
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(session, lookup)
    game = FakeGame(mode="Singles")
    game.begin_time = 100
    game.end_time = 200
    users = [FakeUser(1, "alice"), FakeUser(2, "bob")]
    game_players = [
        FakeGamePlayer(users[0], score=90),
        FakeGamePlayer(users[1], score=70),
    ]

    logs2db.calculate_new_ratings(game, game_players)

    assert len(lookup.added_ratings) == 2
    assert [rating.time for rating in lookup.added_ratings] == [200, 200]
    assert all(rating.mu is not None for rating in lookup.added_ratings)
    assert all(rating.sigma is not None for rating in lookup.added_ratings)
    assert len([item for item in session.added if isinstance(item, FakeRating)]) == 4


def test_calculate_new_ratings_handles_teams(cron_module):
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(FakeSession(), lookup)
    game = FakeGame(mode="Teams")
    game.begin_time = 100
    game.end_time = 200
    game_players = [
        FakeGamePlayer(FakeUser(1, "a"), score=40),
        FakeGamePlayer(FakeUser(2, "b"), score=30),
        FakeGamePlayer(FakeUser(3, "c"), score=50),
        FakeGamePlayer(FakeUser(4, "d"), score=20),
    ]

    logs2db.calculate_new_ratings(game, game_players)

    assert len(lookup.added_ratings) == 4
    assert {rating.rating_type.name for rating in lookup.added_ratings} == {"Teams"}


def test_calculate_new_ratings_ignores_unsupported_modes(cron_module):
    session = FakeSession()
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(session, lookup)
    game = FakeGame(mode="Singles")
    game_players = [FakeGamePlayer(FakeUser(1, "solo"), score=100)]

    logs2db.calculate_new_ratings(game, game_players)

    assert session.added == []
    assert lookup.added_ratings == []


def test_get_trueskill_environment_caches_by_rating_type(cron_module):
    logs2db = cron_module.Logs2DB(FakeSession(), FakeLookup())
    rating_type = types.SimpleNamespace(name="Singles2")

    first = logs2db.get_trueskill_environment(rating_type)
    second = logs2db.get_trueskill_environment(rating_type)

    assert first is second


def test_update_records_tracks_singles_places_and_ties(cron_module):
    session = FakeSession()
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(session, lookup)
    game = FakeGame(mode="Singles")
    users = [FakeUser(1, "alice"), FakeUser(2, "bob"), FakeUser(3, "carol")]
    game_players = [
        FakeGamePlayer(users[0], score=90),
        FakeGamePlayer(users[1], score=90),
        FakeGamePlayer(users[2], score=50),
    ]

    logs2db.update_records(game, game_players)

    assert ujson.decode(lookup.get_record(users[0]).encoded) == [
        [0, 0],
        [1, 0, 0],
        [0, 0, 0, 0],
        [0, 0],
    ]
    assert ujson.decode(lookup.get_record(users[1]).encoded)[1] == [1, 0, 0]
    assert ujson.decode(lookup.get_record(users[2]).encoded)[1] == [0, 0, 1]
    assert len(session.added) == 3


def test_update_records_combines_team_scores(cron_module):
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(FakeSession(), lookup)
    game = FakeGame(mode="Teams")
    users = [FakeUser(1, "a"), FakeUser(2, "b"), FakeUser(3, "c"), FakeUser(4, "d")]
    game_players = [
        FakeGamePlayer(users[0], score=40),
        FakeGamePlayer(users[1], score=30),
        FakeGamePlayer(users[2], score=50),
        FakeGamePlayer(users[3], score=20),
    ]

    logs2db.update_records(game, game_players)

    assert ujson.decode(lookup.get_record(users[0]).encoded)[3] == [1, 0]
    assert ujson.decode(lookup.get_record(users[2]).encoded)[3] == [1, 0]
    assert ujson.decode(lookup.get_record(users[1]).encoded)[3] == [0, 1]
    assert ujson.decode(lookup.get_record(users[3]).encoded)[3] == [0, 1]


def test_update_records_ignores_unsupported_modes(cron_module):
    lookup = FakeLookup()
    logs2db = cron_module.Logs2DB(FakeSession(), lookup)
    game = FakeGame(mode="Casual")

    logs2db.update_records(game, [FakeGamePlayer(FakeUser(1, "alice"), score=100)])

    assert lookup.added_records == []


class Row:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class StatsSession(FakeSession):
    def __init__(self, rows_by_sql):
        super().__init__()
        self.rows_by_sql = rows_by_sql

    def execute(self, sql, params=None):
        self.executions.append((sql, params))
        return self.rows_by_sql.get(sql, [])


def test_statsgen_get_users_with_completed_games_decodes_records(cron_module):
    statsgen = cron_module.StatsGen(
        StatsSession(
            {
                cron_module.StatsGen.users_with_completed_games_sql: [
                    Row(user_id=1, name=b"alice", encoded=ujson.encode([[1, 0], [0, 0, 0], [0, 0, 0, 0], [0, 0]])),
                    Row(user_id=2, name=b"bob", encoded=None),
                ]
            }
        ),
        "unused",
    )

    assert statsgen.get_users_with_completed_games() == [
        [1, "alice", [[1, 0], [0, 0, 0], [0, 0, 0, 0], [0, 0]]],
        [2, "bob", cron_module.get_empty_records()],
    ]


def test_statsgen_output_ratings_groups_rows(cron_module, monkeypatch):
    session = StatsSession(
        {
            cron_module.StatsGen.ratings_sql: [
                Row(name=b"alice", rating_type=b"Singles2", time=100, mu=25.0, sigma=8.0, num_games=3),
                Row(name=b"bob", rating_type=b"Teams", time=200, mu=27.0, sigma=7.5, num_games=5),
            ]
        }
    )
    statsgen = cron_module.StatsGen(session, "unused")
    written = {}
    monkeypatch.setattr(statsgen, "write_file", lambda name, contents: written.update({name: contents}))

    statsgen.output_ratings()

    assert written == {
        "ratings": {
            "Singles2": [[b"alice", 100, 25.0, 8.0, 3]],
            "Teams": [[b"bob", 200, 27.0, 7.5, 5]],
        }
    }


def test_statsgen_output_user_writes_encoded_user_payload(cron_module, monkeypatch):
    session = StatsSession(
        {
            cron_module.StatsGen.user_ratings_sql: [
                Row(name=b"Singles2", time=100, mu=25.0, sigma=8.0),
                Row(name=b"Teams", time=200, mu=27.0, sigma=7.5),
            ],
            cron_module.StatsGen.user_games_sql: [
                Row(game_id=10, end_time=500, game_mode_id=1, player_index=0, name=b"alice", score=90),
                Row(game_id=10, end_time=500, game_mode_id=1, player_index=1, name=b"bob", score=70),
                Row(game_id=9, end_time=400, game_mode_id=4, player_index=0, name=b"alice", score=80),
            ],
        }
    )
    statsgen = cron_module.StatsGen(session, "unused")
    written = {}
    monkeypatch.setattr(statsgen, "write_file", lambda name, contents: written.update({name: contents}))

    statsgen.output_user(123, "a+b/c", [[1, 2], [0, 0, 0], [0, 0, 0, 0], [3, 4]])

    assert written == {
        "users/YStiL2M": {
            "ratings": {
                "Singles2": [100, 25.0, 8.0, [1, 2]],
                "Teams": [200, 27.0, 7.5, [3, 4]],
            },
            "games": [
                [1, 500, [["alice", 90], ["bob", 70]]],
                [4, 400, [["alice", 80]]],
            ],
        }
    }
    assert session.executions == [
        (cron_module.StatsGen.user_ratings_sql, {"user_id": 123}),
        (cron_module.StatsGen.user_games_sql, {"user_id": 123}),
    ]


def test_statsgen_write_file_outputs_json(cron_module, tmp_path):
    output_dir = tmp_path / "stats"
    output_dir.mkdir()
    statsgen = cron_module.StatsGen(FakeSession(), output_dir)

    statsgen.write_file("ratings", {"Singles2": []})

    assert (output_dir / "ratings.json").read_text() == '{"Singles2":[]}'


def test_process_logs_updates_offsets_and_writes_changed_user_stats(
    cron_module, monkeypatch
):
    session = FakeSession()
    lookup = FakeLookup()
    lookup.get_key_value("cron last log timestamp").value = "100"
    lookup.get_key_value("cron last offset").value = "3"
    users = [FakeUser(1, "alice")]
    processed = []
    stats_calls = []

    class FakeLogs2DB:
        def __init__(self, session_arg, lookup_arg):
            assert session_arg is session
            assert lookup_arg is lookup

        def process_logs(self, file, log_timestamp):
            processed.append((file.name, file.tell(), log_timestamp))
            return 7, set(users)

    class FakeStatsGen:
        def __init__(self, session_arg, output_dir):
            assert session_arg is session
            assert output_dir == "stats_temp"

        def output_ratings(self):
            stats_calls.append(("ratings",))

        def output_user(self, user_id, username, records):
            stats_calls.append(("user", user_id, username, records))

    @contextlib.contextmanager
    def session_scope():
        yield session

    def open_log(filename):
        file = io.StringIO("abcdefghi")
        file.name = filename
        return file

    monkeypatch.setattr(cron_module.orm, "session_scope", session_scope)
    monkeypatch.setattr(cron_module.orm, "Lookup", lambda session_arg: lookup)
    monkeypatch.setattr(cron_module, "Logs2DB", FakeLogs2DB)
    monkeypatch.setattr(cron_module, "StatsGen", FakeStatsGen)
    monkeypatch.setattr(
        cron_module.util,
        "get_log_file_filenames",
        lambda log_type, begin: [(100, "first.log"), (200, "second.log")],
    )
    monkeypatch.setattr(cron_module.util, "open_possibly_gzipped_file", open_log)
    monkeypatch.setattr(cron_module.glob, "glob", lambda pattern: [])

    cron_module.process_logs(write_stats_files=True)

    assert processed == [
        ("first.log", 3, 100),
        ("second.log", 0, 200),
    ]
    assert lookup.get_key_value("cron last log timestamp").value == 200
    assert lookup.get_key_value("cron last offset").value == 7
    assert session.flushed is True
    assert stats_calls == [
        ("ratings",),
        ("user", 1, "alice", cron_module.get_empty_records()),
    ]


def test_output_all_stats_files_writes_ratings_and_each_user(
    cron_module, monkeypatch, capsys
):
    session = FakeSession()
    calls = []

    class FakeStatsGen:
        def __init__(self, session_arg, output_dir):
            assert session_arg is session
            assert output_dir == "/tmp/tim/acquire/stats"

        def output_ratings(self):
            calls.append(("ratings",))

        def get_users_with_completed_games(self):
            return [
                [2, "bob", [[0, 1], [0, 0, 0], [0, 0, 0, 0], [0, 0]]],
                [1, "alice", [[1, 0], [0, 0, 0], [0, 0, 0, 0], [0, 0]]],
            ]

        def output_user(self, user_id, username, records):
            calls.append(("user", user_id, username, records))

    @contextlib.contextmanager
    def session_scope():
        yield session

    monkeypatch.setattr(cron_module.orm, "session_scope", session_scope)
    monkeypatch.setattr(cron_module, "StatsGen", FakeStatsGen)

    cron_module.output_all_stats_files()

    assert calls == [
        ("ratings",),
        ("user", 1, "alice", [[1, 0], [0, 0, 0], [0, 0, 0, 0], [0, 0]]),
        ("user", 2, "bob", [[0, 1], [0, 0, 0], [0, 0, 0, 0], [0, 0]]),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "1 alice [[1, 0], [0, 0, 0], [0, 0, 0, 0], [0, 0]]",
        "2 bob [[0, 1], [0, 0, 0], [0, 0, 0, 0], [0, 0]]",
    ]
