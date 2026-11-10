import pytest

from apex.championship.scoring import standings, validate_points
from apex.championship.tie_breaks import beats
from apex.championship.scoring import Standing
from apex.rules import ruleset_for


def test_2026_points_tables():
    rs = ruleset_for(2026)
    assert [rs.points_for("race", p) for p in range(1, 12)] == [25, 18, 15, 12, 10, 8, 6, 4, 2, 1, 0]
    assert [rs.points_for("sprint", p) for p in range(1, 10)] == [8, 7, 6, 5, 4, 3, 2, 1, 0]
    assert rs.points_for("race", None) == 0


def test_no_fastest_lap_bonus_from_2025_but_present_2019_2024():
    assert ruleset_for(2026).points_for("race", 1, fastest_lap=True) == 25
    assert ruleset_for(2023).points_for("race", 1, fastest_lap=True) == 26
    assert ruleset_for(2023).points_for("race", 11, fastest_lap=True) == 0  # outside top 10
    assert ruleset_for(2018).points_for("race", 1, fastest_lap=True) == 25


@pytest.mark.parametrize("frac,expected", [(0.2, 6), (0.4, 13), (0.6, 19), (0.8, 25), (1.0, 25)])
def test_shortened_race_bands(frac, expected):
    assert ruleset_for(2026).points_for("race", 1, distance_fraction=frac) == expected


def test_no_points_before_two_laps_and_sprint_half_distance():
    rs = ruleset_for(2026)
    assert rs.points_for("race", 1, distance_fraction=0.01, leader_laps=1) == 0
    assert rs.points_for("sprint", 1, distance_fraction=0.49) == 0
    assert rs.points_for("sprint", 1, distance_fraction=0.5) == 8


def test_historical_rules_differ():
    assert ruleset_for(2005).race_points[0] == 10
    assert ruleset_for(2021).sprint_points == (3, 2, 1)
    with pytest.raises(KeyError):
        ruleset_for(1950)


def test_2026_standings_match_official(season2026):
    table = standings(season2026)
    top = {s.driver_id: s.points for s in table[:6]}
    assert top == {"antonelli": 390, "max_verstappen": 279, "russell": 262, "hamilton": 261, "leclerc": 249, "norris": 246}
    assert table[0].wins == 9
    assert validate_points(season2026) == []


def test_countback_wins_then_seconds_then_qualifying():
    a, b = Standing("a", 100), Standing("b", 100)
    a.finishes[0], b.finishes[0] = 3, 2
    assert beats(a, b)
    b.finishes[0] = 3
    b.finishes[1] = 1
    assert beats(b, a)
    a.finishes[1] = 1
    a.best_qualifying[0] = 2
    b.best_qualifying[0] = 1
    assert beats(a, b)


def test_disqualified_scores_zero_and_dsq_is_not_a_reliability_dnf(season2026):
    dsq = [r for r in season2026.results if r.position_text == "D"]
    assert dsq and all(r.points == 0 for r in dsq)
    assert all(not r.is_dnf for r in dsq)
