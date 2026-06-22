"""Import legacy game logs into MySQL and generate published stats files.

This module is part of the legacy Python runtime and replay tooling.
"""

import base64
import collections
import glob
import os
import os.path
import subprocess
import time
import traceback
from typing import Protocol, cast

import orm
import sqlalchemy.orm
import sqlalchemy.sql
import sqlalchemy.types
import trueskill
import ujson
import util


class MutableKeyValue(Protocol):
    """Represent the mutable value field on the legacy key/value ORM row."""

    value: str


class Logs2DB:
    """Import parsed log records into ORM objects and rating records."""

    rating_type_to_draw_probability: dict[str, float] = {
        "Singles2": 0.00271,
        "Singles3": 0.00421,
        "Singles4": 0.01664,
        "Teams": 0.00221,
    }

    def __init__(self, session, lookup):
        """Initialize log import state for one database session.

        Args:
            session: SQLAlchemy session used for queries and new rows.
            lookup: Lookup helper used to resolve or create ORM rows.
        """
        self.session = session
        self.lookup = lookup
        self.trueskill_environment_lookup = {}
        self.completed_game_users = None

        self.method_lookup = {
            "game": self.process_game,
            "game-player": self.process_game_player,
            "game-result": self.process_game_result,
        }

    def process_logs(self, file, log_time=None):
        """Process logs.

        Args:
            file: Open text file or file-like object to read.
            log_time: Timestamp identifying the source log file.

        Returns:
            Updated byte offset and set of users whose completed games changed.
        """
        len_last_line = 0
        self.completed_game_users = set()
        for line in file:
            if line and line[-1] == "\n":
                if line[0] == "{":
                    params = ujson.decode(line)
                    if "log-time" not in params:
                        params["log-time"] = log_time
                    method = self.method_lookup.get(params.get("_"))
                    if method:
                        method(params)
            else:
                len_last_line = len(line.encode())
        return file.tell() - len_last_line, self.completed_game_users

    def process_game(self, params):
        """Process game.

        Args:
            params: Decoded log entry parameters.
        """
        game = self.lookup.get_game(params["log-time"], params["game-id"])

        begin_time = params.get("begin")
        if begin_time:
            game.begin_time = begin_time

        end_time = params.get("end")
        if end_time:
            game.end_time = end_time

        game.game_state = self.lookup.get_game_state(params["state"])

        game_mode = params.get("mode")
        if game_mode:
            game.game_mode = self.lookup.get_game_mode(game_mode)

        score = params.get("score")
        if score:
            params["scores"] = score
            self.process_game_result(params)

    def process_game_player(self, params):
        """Process game player.

        Args:
            params: Decoded log entry parameters.
        """
        game = self.lookup.get_game(params["log-time"], params["game-id"])
        game_player = self.lookup.get_game_player(game, params["player-id"])
        game_player.user = self.lookup.get_user(params["username"])

    def process_game_result(self, params):
        """Process game result.

        Args:
            params: Decoded log entry parameters.
        """
        game = self.lookup.get_game(params["log-time"], params["game-id"])

        game_players = []
        for player_index, score in enumerate(params["scores"]):
            game_player = self.lookup.get_game_player(game, player_index)
            game_player.score = score
            game_players.append(game_player)
            assert self.completed_game_users is not None
            self.completed_game_users.add(game_player.user)

        self.calculate_new_ratings(game, game_players)
        self.update_records(game, game_players)

    def calculate_new_ratings(self, game, game_players):
        """Calculate new ratings.

        Args:
            game: Game or game-like object being updated.
            game_players: Game player rows participating in the completed game.
        """
        game_mode_name = game.game_mode.name
        num_players = len(game_players)
        if game_mode_name == "Teams":
            rating_type = self.lookup.get_rating_type("Teams")
        elif game_mode_name == "Singles" and 2 <= num_players <= 4:
            rating_type = self.lookup.get_rating_type("Singles" + str(num_players))
        else:
            return

        trueskill_ratings = []
        for game_player in game_players:
            rating = self.lookup.get_rating(game_player.user, rating_type)
            if not rating:
                rating = orm.Rating(
                    user=game_player.user,
                    rating_type=rating_type,
                    time=game.begin_time,
                    mu=trueskill.MU,
                    sigma=trueskill.SIGMA,
                )
                self.session.add(rating)
            trueskill_rating = trueskill.Rating(rating.mu, rating.sigma)
            trueskill_ratings.append(trueskill_rating)

        new_ratings = [
            orm.Rating(user=game_player.user, rating_type=rating_type, time=game.end_time)
            for game_player in game_players
        ]
        self.session.add_all(new_ratings)

        trueskill_environment = self.get_trueskill_environment(rating_type)

        if game_mode_name == "Teams":
            rating_groups = [
                [trueskill_ratings[0], trueskill_ratings[2]],
                [trueskill_ratings[1], trueskill_ratings[3]],
            ]
            ranks = [
                -(game_players[0].score + game_players[2].score),
                -(game_players[1].score + game_players[3].score),
            ]
            rating_groups_result = trueskill_environment.rate(rating_groups, ranks)
            new_ratings[0].mu = rating_groups_result[0][0].mu
            new_ratings[0].sigma = rating_groups_result[0][0].sigma
            new_ratings[1].mu = rating_groups_result[1][0].mu
            new_ratings[1].sigma = rating_groups_result[1][0].sigma
            new_ratings[2].mu = rating_groups_result[0][1].mu
            new_ratings[2].sigma = rating_groups_result[0][1].sigma
            new_ratings[3].mu = rating_groups_result[1][1].mu
            new_ratings[3].sigma = rating_groups_result[1][1].sigma
        else:
            rating_groups = [[trueskill_rating] for trueskill_rating in trueskill_ratings]
            ranks = [[-game_player.score] for game_player in game_players]
            rating_groups_result = trueskill_environment.rate(rating_groups, ranks)
            for player_index, rating_group_result in enumerate(rating_groups_result):
                new_ratings[player_index].mu = rating_group_result[0].mu
                new_ratings[player_index].sigma = rating_group_result[0].sigma

        for rating in new_ratings:
            self.lookup.add_rating(rating)

    def get_trueskill_environment(self, rating_type):
        """Get trueskill environment.

        Ratings are persisted incrementally as cron imports new completed games,
        so this must continue using the same TrueSkill-compatible calculation
        until existing rating histories can be rebuilt or migrated to separate
        OpenSkill rating types.

        Args:
            rating_type: Rating type ORM object or name, depending on the caller.

        Returns:
            Cached TrueSkill environment configured for the rating type.
        """
        trueskill_environment = self.trueskill_environment_lookup.get(rating_type.name)
        if trueskill_environment:
            return trueskill_environment

        trueskill_environment = trueskill.TrueSkill(
            beta=trueskill.SIGMA,
            draw_probability=Logs2DB.rating_type_to_draw_probability[rating_type.name],
        )

        self.trueskill_environment_lookup[rating_type.name] = trueskill_environment
        return trueskill_environment

    def update_records(self, game, game_players):
        """Update records.

        Args:
            game: Game or game-like object being updated.
            game_players: Game player rows participating in the completed game.
        """
        record_index = None
        game_mode_name = game.game_mode.name
        if game_mode_name == "Singles":
            if len(game_players) == 2:
                record_index = 0
            elif len(game_players) == 3:
                record_index = 1
            elif len(game_players) == 4:
                record_index = 2
        elif game_mode_name == "Teams":
            record_index = 3

        if record_index is None:
            return

        users_and_scores = [[[gp.user], gp.score] for gp in game_players]
        if game_mode_name == "Teams":
            users_and_scores = [
                [
                    [users_and_scores[0][0][0], users_and_scores[2][0][0]],
                    users_and_scores[0][1] + users_and_scores[2][1],
                ],
                [
                    [users_and_scores[1][0][0], users_and_scores[3][0][0]],
                    users_and_scores[1][1] + users_and_scores[3][1],
                ],
            ]

        users_and_scores.sort(key=lambda us: -us[1])

        previous_score = -1
        previous_place = -1
        for index, [users, score] in enumerate(users_and_scores):
            if score == previous_score:
                place = previous_place
            else:
                place = index
                previous_score = score
                previous_place = index

            for user in users:
                record = self.lookup.get_record(user)
                if record is None:
                    record = orm.Record(user=user, encoded="")
                    decoded = get_empty_records()
                    self.lookup.add_record(record)
                    self.session.add(record)
                else:
                    decoded = ujson.decode(record.encoded)

                decoded[record_index][place] += 1

                record.encoded = ujson.encode(decoded)


def get_empty_records() -> list[list[int]]:
    """Get empty records.

    Returns:
        Initial encoded record structure for a user with no stats.
    """
    return [
        [0, 0],  # Singles2
        [0, 0, 0],  # Singles3
        [0, 0, 0, 0],  # Singles4
        [0, 0],  # Teams
    ]


class StatsGen:
    """Generate JSON stats files from persisted game and rating data."""

    users_with_completed_games_sql = sqlalchemy.sql.text(
        """
        select distinct user.user_id,
            user.name,
            record.encoded
        from user
        join game_player on user.user_id = game_player.user_id
        join game on game_player.game_id = game.game_id
        left join record on user.user_id = record.user_id
        where game.end_time is not null
        order by user.user_id asc
        """
    )
    ratings_sql = sqlalchemy.sql.text(
        """
        select user.name,
            rating_type.name as rating_type,
            rating.time,
            rating.mu,
            rating.sigma,
            rating_summary.num_games
        from rating
        join (
            select max(rating_id) as rating_id,
                count(rating_id) - 1 as num_games
            from rating
            group by user_id, rating_type_id
        ) rating_summary on rating.rating_id = rating_summary.rating_id
        join rating_type on rating.rating_type_id = rating_type.rating_type_id
        join user on rating.user_id = user.user_id
        where rating.time >= unix_timestamp() - 30 * 24 * 60 * 60
        order by rating.mu - rating.sigma * 3 desc,
            rating.mu desc, rating.time asc, rating.user_id asc
        """
    )
    user_ratings_sql = sqlalchemy.sql.text(
        """
        select rating_type.name,
            rating.time,
            rating.mu,
            rating.sigma
        from rating
        join (
            select max(rating_id) as rating_id
            from rating
            where rating.user_id = :user_id
            group by rating_type_id
        ) rating_summary on rating.rating_id = rating_summary.rating_id
        join rating_type on rating.rating_type_id = rating_type.rating_type_id
        order by rating_type.name
        """
    )
    user_games_sql = sqlalchemy.sql.text(
        """
        select game.game_id,
            game.end_time,
            game.game_mode_id,
            game_player.player_index,
            user.name,
            game_player.score
        from game
        join (
            select game.game_id
            from game
            join game_player on game.game_id = game_player.game_id
            where game_player.user_id = :user_id
                and game_player.score is not null
            order by game.end_time desc, game.game_id desc
            limit 100
        ) game_ids on game.game_id = game_ids.game_id
        join game_player on game.game_id = game_player.game_id
        join user on game_player.user_id = user.user_id
        order by game.end_time desc, game.game_id desc, game_player.player_index asc
        """
    )

    def __init__(self, session, output_dir):
        """Initialize stats generation state for one database session.

        Args:
            session: SQLAlchemy session used for queries and new rows.
            output_dir: Directory where generated artifacts should be written.
        """
        self.session = session
        self.output_dir = output_dir

    def get_users_with_completed_games(self):
        """Get users with completed games.

        Returns:
            Rows containing user id, username, and decoded records.
        """
        users_with_completed_games = []
        for row in self.session.execute(StatsGen.users_with_completed_games_sql):
            decoded = ujson.decode(row.encoded) if row.encoded else get_empty_records()
            users_with_completed_games.append(
                [row.user_id, decode_database_text(row.name), decoded]
            )
        return users_with_completed_games

    def output_ratings(self):
        """Output ratings."""
        rating_type_to_ratings = collections.defaultdict(list)
        for row in self.session.execute(StatsGen.ratings_sql):
            rating_type_to_ratings[decode_database_text(row.rating_type)].append(
                [decode_database_text(row.name), row.time, row.mu, row.sigma, row.num_games]
            )

        self.write_file("ratings", rating_type_to_ratings)

    def output_user(self, user_id, username, records):
        """Output user.

        Args:
            user_id: Persisted user id whose stats file should be written.
            username: Player username from the client or log.
            records: Encoded per-user stats records.
        """
        ratings = {}
        for row in self.session.execute(StatsGen.user_ratings_sql, {"user_id": user_id}):
            ratings[decode_database_text(row.name)] = [row.time, row.mu, row.sigma]

        games = []
        last_game_id = None
        for row in self.session.execute(StatsGen.user_games_sql, {"user_id": user_id}):
            if row.game_id != last_game_id:
                games.append([row.game_mode_id, row.end_time, []])
            games[-1][2].append([decode_database_text(row.name), row.score])
            last_game_id = row.game_id

        for record_key in ratings:
            ratings[record_key].append(records[record_key_to_record_index[record_key]])

        self.write_file(
            "users/"
            + base64.b64encode(username.encode())
            .decode()
            .replace("=", "")
            .replace("+", "-")
            .replace("/", "_"),
            {"ratings": ratings, "games": games},
        )

    def write_file(self, filename_prefix, contents):
        """Write file.

        Args:
            filename_prefix: Output filename prefix without extension.
            contents: Text content to write.
        """
        with open(os.path.join(self.output_dir, filename_prefix + ".json"), "w") as f:
            f.write(ujson.dumps(contents))


def decode_database_text(value: bytes | str) -> str:
    """Return text from legacy byte rows or modern string rows.

    Raw SQL result rows may contain `bytes` with the legacy connector and `str`
    with modern mysql-connector-python. Stats generation uses this helper at
    the database/output boundary so JSON serialization receives plain strings
    regardless of which connector produced the row.

    Args:
        value: Database text value returned as `bytes` or `str`.

    Returns:
        Decoded string value.
    """
    if isinstance(value, bytes):
        return value.decode()
    return value


record_key_to_record_index: dict[str, int] = {
    "Singles2": 0,
    "Singles3": 1,
    "Singles4": 2,
    "Teams": 3,
}


def process_logs(write_stats_files: bool) -> None:
    """Process logs.

    Args:
        write_stats_files: Whether to generate public stats files after import.
    """
    with orm.session_scope() as session:
        lookup = orm.Lookup(session)
        logs2db = Logs2DB(session, lookup)

        kv_last_log_timestamp = lookup.get_key_value("cron last log timestamp")
        last_log_timestamp = (
            1408905413 if kv_last_log_timestamp.value is None else int(kv_last_log_timestamp.value)
        )
        kv_last_offset = lookup.get_key_value("cron last offset")
        last_offset = 0 if kv_last_offset.value is None else int(kv_last_offset.value)

        completed_game_users = set()
        for log_timestamp, filename in util.get_log_file_filenames("py", begin=last_log_timestamp):
            if log_timestamp != last_log_timestamp:
                last_offset = 0

            with util.open_possibly_gzipped_file(filename) as f:
                if last_offset:
                    f.seek(last_offset)
                last_offset, new_completed_game_users = logs2db.process_logs(f, log_timestamp)
                completed_game_users.update(new_completed_game_users)

            last_log_timestamp = log_timestamp

        cast(MutableKeyValue, kv_last_log_timestamp).value = str(last_log_timestamp)
        cast(MutableKeyValue, kv_last_offset).value = str(last_offset)

        session.flush()

        if write_stats_files and completed_game_users:
            statsgen = StatsGen(session, "stats_temp")
            statsgen.output_ratings()
            for user in completed_game_users:
                record = lookup.get_record(user)
                decoded = ujson.decode(cast(str, record.encoded)) if record else get_empty_records()
                statsgen.output_user(cast(int, user.user_id), cast(str, user.name), decoded)

            ratings_filenames = glob.glob("stats_temp/*.json")
            users_filenames = glob.glob("stats_temp/users/*.json")
            if ratings_filenames:
                command = ["zopfli"]
                command.extend(ratings_filenames)
                command.extend(users_filenames)
                subprocess.call(command)

                ratings_filenames = ratings_filenames + [x + ".gz" for x in ratings_filenames]
                users_filenames = users_filenames + [x + ".gz" for x in users_filenames]

                command = ["touch", "-r", "stats_temp/ratings.json"]
                command.extend(ratings_filenames)
                command.extend(users_filenames)
                subprocess.call(command)

                command = ["mv"]
                command.extend(ratings_filenames)
                command.append("web/stats/data")
                subprocess.call(command)

                command = ["mv"]
                command.extend(users_filenames)
                command.append("web/stats/data/users")
                subprocess.call(command)


def output_all_stats_files() -> None:
    """Output all stats files."""
    with orm.session_scope() as session:
        statsgen = StatsGen(session, "/tmp/tim/acquire/stats")
        statsgen.output_ratings()
        users_with_completed_games = statsgen.get_users_with_completed_games()
        for [user_id, username, records] in sorted(users_with_completed_games):
            print(user_id, username, records)
            statsgen.output_user(user_id, username, records)


def main() -> None:
    """Run the module command-line entry point."""
    while True:
        try:
            process_logs(True)
        except BaseException:
            print(traceback.format_exc())

        time.sleep(60)


if __name__ == "__main__":
    # process_logs(False)
    # output_all_stats_files()
    main()
