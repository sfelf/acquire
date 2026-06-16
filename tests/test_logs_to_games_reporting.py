import pickle

import pytest


pytestmark = pytest.mark.unit


def write_report_fixture(tmp_path, mode_to_game_data):
    path = tmp_path / "first_merge_bonuses_and_final_scores_of_all_completed_games.bin"
    with path.open("wb") as file:
        pickle.dump(mode_to_game_data, file)


def make_mode_data():
    singles2 = [
        ({0: {0: 7, 1: 3}}, [90, 70]),
        ({0: {0: 4, 1: 4}}, [60, 80]),
        ({0: {0: 5, 1: 1}}, [50, 50]),
    ]
    teams = [
        ({0: {0: 8, 1: 2}}, [40, 30, 50, 20]),
        ({0: {2: 7, 3: 1}}, [10, 60, 20, 50]),
    ]
    return {
        "Singles2": singles2,
        "Singles3": [],
        "Singles4": [],
        "Teams": teams,
    }


def test_get_player_id_to_ranking_handles_ties(logs_to_games_without_database):
    assert logs_to_games_without_database.get_player_id_to_ranking([90, 70, 70, 50]) == {
        0: 1,
        1: 2,
        2: 2,
        3: 4,
    }


def test_print_table_aligns_columns(logs_to_games_without_database, capsys):
    logs_to_games_without_database.print_table(
        [
            ["Rank", "Count"],
            ["1", "10/12"],
            ["N/A", "2/12"],
        ]
    )

    assert capsys.readouterr().out.splitlines() == [
        "Rank  Count",
        "   1  10/12",
        " N/A   2/12",
    ]


def test_report_on_player_ranking_distribution_outputs_counts(
    logs_to_games_without_database,
    tmp_path,
    capsys,
):
    write_report_fixture(tmp_path, make_mode_data())

    logs_to_games_without_database.report_on_player_ranking_distribution(tmp_path)

    assert capsys.readouterr().out.splitlines() == [
        "Singles2",
        "(1, 2) 2",
        "(1, 1) 1",
        "",
        "Singles3",
        "",
        "Singles4",
        "",
        "Teams",
        "(1, 2) 2",
        "",
    ]


def test_report_on_first_merge_bonuses_and_final_scores_outputs_bucket_tables(
    logs_to_games_without_database,
    tmp_path,
    capsys,
):
    write_report_fixture(tmp_path, make_mode_data())

    logs_to_games_without_database.report_on_first_merge_bonuses_and_final_scores_of_all_completed_games(
        tmp_path
    )

    assert capsys.readouterr().out.splitlines() == [
        "Singles2",
        "  1  2/2  100.0%  1/2  50.0%",
        "N/A  1/3   33.3%  1/2  50.0%",
        "",
        "Singles3",
        "N/A",
        "",
        "Singles4",
        "N/A",
        "",
        "Teams",
        "  1  1/2  50.0%  1/2  50.0%  2/4  50.0%",
        "  2  1/2  50.0%  1/2  50.0%  2/4  50.0%",
        "N/A  0/2   0.0%  0/2   0.0%  0/4   0.0%",
        "",
    ]
