"""Import legacy game logs into Postgres and generate published stats files."""

import argparse
import base64
import collections
import glob
import os
import os.path
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Never, Protocol, cast

import sqlalchemy.orm
import sqlalchemy.sql
import sqlalchemy.types
import ujson

from acquire import util

RECENT_RATINGS_WINDOW_SECONDS = 30 * 24 * 60 * 60
STATS_UPDATE_INTERVAL_SECONDS = 60
SOURCE_PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_STATS_DATA_ROOT = SOURCE_PROJECT_ROOT / "client" / "stats" / "data"
SOURCE_STATS_TEMP_ROOT = SOURCE_PROJECT_ROOT / "server" / "stats_temp"
STATS_DATA_ROOT_ENV = "ACQUIRE_STATS_DATA_ROOT"
STATS_TEMP_ROOT_ENV = "ACQUIRE_STATS_TEMP_ROOT"


def _resolve_stats_root(
    explicit_root: Path | None,
    environment_name: str,
    source_root: Path,
    source_anchor: Path,
) -> Path:
    """Resolve one stats root from an argument, configuration, or source layout.

    Args:
        explicit_root: Caller-supplied root, when available.
        environment_name: Environment variable containing an installed root.
        source_root: Default root for editable and container source layouts.
        source_anchor: Existing source directory that validates the fallback.

    Returns:
        Resolved filesystem root.

    Raises:
        RuntimeError: If neither configuration nor a source layout is available.
        ValueError: If an explicit or environment-provided root is not absolute.
    """
    if explicit_root is not None:
        if not explicit_root.is_absolute():
            raise ValueError(f"{environment_name} must be an absolute path")
        return explicit_root

    configured_root = os.environ.get(environment_name)
    if configured_root:
        root = Path(configured_root)
        if not root.is_absolute():
            raise ValueError(f"{environment_name} must be an absolute path")
        return root

    if source_anchor.is_dir():
        return source_root

    raise RuntimeError(
        f"{environment_name} must be set when acquire is installed outside its source layout"
    )


def resolve_stats_roots(
    stats_data_root: Path | None = None,
    stats_temp_root: Path | None = None,
) -> tuple[Path, Path]:
    """Resolve publication and staging roots for stats generation.

    Installed artifacts do not contain the generated client tree or a staging
    directory. Operators must configure both absolute roots in that layout;
    editable installs and the production source-layout image retain their
    existing repository-relative locations.

    Args:
        stats_data_root: Explicit published-data root, if supplied by a caller.
        stats_temp_root: Explicit staging root, if supplied by a caller.

    Returns:
        Published-data and staging roots, in that order.
    """
    return (
        _resolve_stats_root(
            stats_data_root,
            STATS_DATA_ROOT_ENV,
            SOURCE_STATS_DATA_ROOT,
            SOURCE_PROJECT_ROOT / "client" / "stats",
        ),
        _resolve_stats_root(
            stats_temp_root,
            STATS_TEMP_ROOT_ENV,
            SOURCE_STATS_TEMP_ROOT,
            SOURCE_PROJECT_ROOT / "server",
        ),
    )


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
        import trueskill

        from acquire import orm

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
        import trueskill

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
        from acquire import orm

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
        select distinct "user".user_id,
            "user".name,
            record.encoded
        from "user"
        join game_player on "user".user_id = game_player.user_id
        join game on game_player.game_id = game.game_id
        left join record on "user".user_id = record.user_id
        where game.end_time is not null
        order by "user".user_id asc
        """
    )
    ratings_sql = sqlalchemy.sql.text(
        """
        select "user".name,
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
        join "user" on rating.user_id = "user".user_id
        where rating.time >= :minimum_rating_time
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
            "user".name,
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
        join "user" on game_player.user_id = "user".user_id
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

    def users_with_completed_games_sql_for_session(self):
        """Return the completed-game users query.

        Returns:
            SQLAlchemy text query for Postgres.
        """
        return StatsGen.users_with_completed_games_sql

    def get_users_with_completed_games(self):
        """Get users with completed games.

        Returns:
            Rows containing user id, username, and decoded records.
        """
        users_with_completed_games = []
        for row in self.session.execute(self.users_with_completed_games_sql_for_session()):
            decoded = ujson.decode(row.encoded) if row.encoded else get_empty_records()
            users_with_completed_games.append(
                [row.user_id, decode_database_text(row.name), decoded]
            )
        return users_with_completed_games

    def ratings_sql_for_session(self):
        """Return the ratings summary SQL.

        Returns:
            SQLAlchemy text query for Postgres.
        """
        return StatsGen.ratings_sql

    def user_games_sql_for_session(self):
        """Return the user game history SQL.

        Returns:
            SQLAlchemy text query for Postgres.
        """
        return StatsGen.user_games_sql

    def output_ratings(self):
        """Write the public ratings summary for recently active players.

        The cutoff is computed in Python so the published ratings file includes
        only latest ratings with activity in the rolling 30-day window used by
        the legacy cron job.
        """
        rating_type_to_ratings = collections.defaultdict(list)
        minimum_rating_time = int(time.time()) - RECENT_RATINGS_WINDOW_SECONDS
        for row in self.session.execute(
            self.ratings_sql_for_session(),
            {"minimum_rating_time": minimum_rating_time},
        ):
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
        for row in self.session.execute(self.user_games_sql_for_session(), {"user_id": user_id}):
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
    """Return text from byte rows or modern string rows.

    Stats generation uses this helper at the database/output boundary so JSON
    serialization receives plain strings even when a test double or historical
    adapter supplies bytes.

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


def process_logs(
    write_stats_files: bool,
    *,
    stats_data_root: Path | None = None,
    stats_temp_root: Path | None = None,
) -> None:
    """Import new log records and optionally publish browser stats data.

    Generated ratings and per-user files are moved into the stats client's
    gitignored data directory after compression. The FastAPI gateway serves
    that directory under `/stats/data/`, so cron and the browser share one
    publication tree regardless of the process working directory.

    Args:
        write_stats_files: Whether to generate public stats files after import.
        stats_data_root: Directory where generated stats JSON is published, or
            `None` to resolve it from installed configuration or the source layout.
        stats_temp_root: Directory where stats files are staged before publishing,
            or `None` to resolve it from configuration or the source layout.
    """
    from acquire import orm

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
            stats_data_root, stats_temp_root = resolve_stats_roots(
                stats_data_root,
                stats_temp_root,
            )
            stats_temp_root.mkdir(parents=True, exist_ok=True)
            (stats_temp_root / "users").mkdir(parents=True, exist_ok=True)
            statsgen = StatsGen(session, stats_temp_root)
            statsgen.output_ratings()
            for user in completed_game_users:
                record = lookup.get_record(user)
                decoded = ujson.decode(cast(str, record.encoded)) if record else get_empty_records()
                statsgen.output_user(cast(int, user.user_id), cast(str, user.name), decoded)

            ratings_filenames = glob.glob(os.fspath(stats_temp_root / "*.json"))
            users_filenames = glob.glob(os.fspath(stats_temp_root / "users" / "*.json"))
            if ratings_filenames:
                users_stats_data_root = stats_data_root / "users"
                users_stats_data_root.mkdir(parents=True, exist_ok=True)

                publish_stats_files(
                    stats_data_root,
                    stats_temp_root,
                    ratings_filenames,
                    users_filenames,
                )


def publish_stats_files(
    stats_data_root: Path,
    stats_temp_root: Path,
    ratings_filenames: Sequence[str],
    users_filenames: Sequence[str],
) -> None:
    """Compress and publish staged stats files.

    External command failures propagate so the surrounding database transaction
    rolls back its log offsets. Staged JSON and gzip files are removed after a
    failed attempt, allowing the continuous updater to regenerate a coherent
    set on its next retry. Files already moved to publication remain valid and
    may be replaced by that retry.

    Args:
        stats_data_root: Published stats-data directory.
        stats_temp_root: Staging directory containing generated JSON files.
        ratings_filenames: Staged top-level ratings JSON files.
        users_filenames: Staged per-user JSON files.

    Raises:
        OSError: A staging cleanup or publication command cannot complete.
        subprocess.CalledProcessError: A publication command exits unsuccessfully.
    """
    staged_filenames = [*ratings_filenames, *users_filenames]
    compressed_filenames = [filename + ".gz" for filename in staged_filenames]
    cleanup_paths = [Path(filename) for filename in [*staged_filenames, *compressed_filenames]]

    for compressed_path in cleanup_paths[len(staged_filenames) :]:
        compressed_path.unlink(missing_ok=True)

    try:
        subprocess.run(
            ["zopfli", *staged_filenames],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        published_filenames = [
            *ratings_filenames,
            *(filename + ".gz" for filename in ratings_filenames),
        ]
        published_users_filenames = [
            *users_filenames,
            *(filename + ".gz" for filename in users_filenames),
        ]
        subprocess.run(
            [
                "touch",
                "-r",
                os.fspath(stats_temp_root / "ratings.json"),
                *published_filenames,
                *published_users_filenames,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["mv", *published_filenames, os.fspath(stats_data_root)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["mv", *published_users_filenames, os.fspath(stats_data_root / "users")],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        for cleanup_path in cleanup_paths:
            cleanup_path.unlink(missing_ok=True)
        raise


def output_all_stats_files() -> None:
    """Output all stats files."""
    from acquire import orm

    with orm.session_scope() as session:
        statsgen = StatsGen(session, "/tmp/tim/acquire/stats")
        statsgen.output_ratings()
        users_with_completed_games = statsgen.get_users_with_completed_games()
        for [user_id, username, records] in sorted(users_with_completed_games):
            print(user_id, username, records)
            statsgen.output_user(user_id, username, records)


class StatsArgumentParser(argparse.ArgumentParser):
    """Parse stats command arguments without reflecting configured paths.

    Publication and staging roots may contain private deployment identifiers.
    Invalid input therefore exits with a fixed diagnostic rather than argparse
    output containing the supplied value.
    """

    def error(self, message: str) -> Never:
        """Exit with a fixed invalid-argument diagnostic.

        Args:
            message: Argparse-generated error text, intentionally ignored.
        """
        self.exit(2, "error: invalid arguments\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the installed stats-updater arguments.

    Both roots are optional so the command can use its documented environment
    or validated source-layout fallbacks. Explicit values are checked for
    absolute paths here without resolving configuration or initializing the
    database.

    Args:
        argv: Arguments to parse, or `None` to use process arguments.

    Returns:
        Namespace containing optional explicit publication and staging roots.
    """
    parser = StatsArgumentParser(
        prog="acquire-update-stats",
        description="Continuously import logs and publish updated stats files.",
        allow_abbrev=False,
    )
    parser.add_argument("--stats-data-root", type=Path)
    parser.add_argument("--stats-temp-root", type=Path)
    args = parser.parse_args(argv)
    configured_roots = (args.stats_data_root, args.stats_temp_root)
    if any(root is not None and not root.is_absolute() for root in configured_roots):
        parser.error("stats roots must be absolute")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run the installed continuous stats updater.

    Roots are validated before ORM initialization, so help and configuration
    errors require no live database. Each successful or failed update is
    followed by the legacy 60-second interval. Operational failures emit a
    fixed diagnostic and retry without exposing database values, filesystem
    paths, log contents, or exception representations. Interruption exits with
    status 130.

    Args:
        argv: Arguments to parse, or `None` to use process arguments.

    Returns:
        `1` for invalid installed-layout configuration or `130` on interruption.
    """
    args = parse_args(argv)
    try:
        stats_data_root, stats_temp_root = resolve_stats_roots(
            args.stats_data_root,
            args.stats_temp_root,
        )
    except Exception:
        print("error: stats configuration failed", file=sys.stderr)
        return 1

    while True:
        try:
            process_logs(
                True,
                stats_data_root=stats_data_root,
                stats_temp_root=stats_temp_root,
            )
        except KeyboardInterrupt:
            return 130
        except Exception:
            print("error: stats update failed", file=sys.stderr)

        try:
            time.sleep(STATS_UPDATE_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
