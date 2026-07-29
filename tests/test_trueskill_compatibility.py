import pytest
import trueskill

from acquire.stats import Logs2DB

pytestmark = pytest.mark.unit

TRUESKILL_0_4_4_BASELINE = {
    "Singles2": (
        (28.331141898505834, 7.641218430816306),
        (21.668858101494155, 7.641218430816306),
    ),
    "Singles3": (
        (30.008768336351682, 7.353118588082748),
        (25.00000000000455, 7.096014433629911),
        (19.991231663643756, 7.353118588083461),
    ),
    "Singles4": (
        (31.178243444110986, 7.18239867463923),
        (26.790288369682507, 6.869434053168428),
        (23.209711630355038, 6.869434053165958),
        (18.821756555879848, 7.182398674643774),
    ),
    "Teams": (
        (27.354641229959626, 7.995038570619282),
        (27.354641229959626, 7.995038570619282),
        (22.645358770040378, 7.995038570619282),
        (22.645358770040378, 7.995038570619282),
    ),
}


@pytest.mark.parametrize(
    ("rating_type", "scores"),
    [
        ("Singles2", (100, 80)),
        ("Singles3", (100, 80, 60)),
        ("Singles4", (100, 80, 60, 40)),
    ],
)
def test_trueskill_0_4_5_preserves_singles_rating_baselines(
    rating_type,
    scores,
):
    environment = trueskill.TrueSkill(
        beta=trueskill.SIGMA,
        draw_probability=Logs2DB.rating_type_to_draw_probability[rating_type],
    )
    result = environment.rate(
        [[trueskill.Rating()] for _ in scores],
        [[-score] for score in scores],
    )
    actual = tuple(
        value
        for rating_group in result
        for rating in rating_group
        for value in (rating.mu, rating.sigma)
    )
    expected = tuple(
        value
        for baseline_rating in TRUESKILL_0_4_4_BASELINE[rating_type]
        for value in baseline_rating
    )

    assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_trueskill_0_4_5_preserves_teams_rating_baseline():
    environment = trueskill.TrueSkill(
        beta=trueskill.SIGMA,
        draw_probability=Logs2DB.rating_type_to_draw_probability["Teams"],
    )
    ratings = [trueskill.Rating() for _ in range(4)]
    result = environment.rate(
        [[ratings[0], ratings[2]], [ratings[1], ratings[3]]],
        [-160, -120],
    )
    actual = tuple(
        value
        for rating_group in result
        for rating in rating_group
        for value in (rating.mu, rating.sigma)
    )
    expected = tuple(
        value
        for baseline_rating in TRUESKILL_0_4_4_BASELINE["Teams"]
        for value in baseline_rating
    )

    assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12)
