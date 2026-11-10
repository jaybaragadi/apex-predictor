from dataclasses import replace

from apex.championship.elimination import ALIVE, CLINCHED, ELIMINATED, CHAMPION, championship_status
from apex.rules import ruleset_for
from conftest import make_season


def test_2026_antonelli_clinched_after_mexico(season2026):
    st = championship_status(season2026)
    assert st["clinched"] and st["champion"] == "antonelli"
    assert st["drivers"]["antonelli"]["status"] == CLINCHED
    assert st["remaining_grands_prix"] == 3 and st["max_points_available"] == 75
    assert all(s["status"] == ELIMINATED for d, s in st["drivers"].items() if d != "antonelli")
    assert st["clinch_round"] == 19


def test_not_clinched_earlier(season2026):
    st = championship_status(season2026.truncated(18))
    assert not st["clinched"]
    alive = {d for d, s in st["drivers"].items() if s["status"] == ALIVE}
    assert {"antonelli", "russell", "hamilton"} <= alive
    assert st["drivers"]["max_verstappen"]["status"] == ELIMINATED


def test_leader_beyond_remaining_maximum():
    s = make_season({"a": 100, "b": 74}, remaining=3)  # b max = 74+75 = 149 > 100 -> alive
    assert championship_status(s)["drivers"]["b"]["status"] == ALIVE
    s = make_season({"a": 100, "b": 24}, remaining=3)  # 24+75 = 99 < 100
    st = championship_status(s)
    assert st["drivers"]["b"]["status"] == ELIMINATED
    assert st["clinched"] and st["champion"] == "a"


def test_equality_resolved_by_countback():
    # b can at most tie a on 100. a already has 1 win (position 1 in round 1).
    s = make_season({"a": 75, "b": 50}, remaining=1)
    # b wins the last race -> 75 points, 1 win each; deeper countback undecidable
    # a priori -> conservatively alive, flagged.
    d = championship_status(s)["drivers"]["b"]
    assert d["status"] == ALIVE and d["tie_break_uncertain"]
    # If b cannot reach a tie it is eliminated.
    s = make_season({"a": 76, "b": 50}, remaining=1)
    assert championship_status(s)["drivers"]["b"]["status"] == ELIMINATED


def test_multiple_contenders_and_season_over():
    s = make_season({"a": 50, "b": 45, "c": 40}, remaining=2)
    st = championship_status(s)
    assert sum(v["status"] == ALIVE for v in st["drivers"].values()) == 3
    s = make_season({"a": 50, "b": 45}, remaining=0)
    st = championship_status(s)
    assert st["drivers"]["a"]["status"] == CHAMPION and st["clinched"]


def test_full_field_cp_sat_detects_interacting_rivals():
    # Three-car field: c can only win if BOTH a and d score <= 1 point in the
    # final race. Points bound says alive, but with every car classified the
    # 2nd/3rd places (18/15) must go to a and d -> impossible.
    s = make_season({"a": 100, "d": 100, "c": 76}, remaining=1)
    st = championship_status(s)
    c = st["drivers"]["c"]
    assert c["status"] == ALIVE  # mathematically alive (rivals could retire)
    assert c["alive_if_all_finish"] is False


def test_full_field_feasible_when_slots_can_be_spread():
    s = make_season({"a": 100, "b": 90}, remaining=2, field_size=20)
    st = championship_status(s)
    assert st["drivers"]["b"]["alive_if_all_finish"] is True


def test_cancelled_race_removed_from_remaining():
    s = make_season({"a": 100, "b": 60}, remaining=2)  # b max 110 -> alive
    assert championship_status(s)["drivers"]["b"]["status"] == ALIVE
    s.events[-1].status = "cancelled"  # only 25 left -> 85 < 100
    assert championship_status(s)["drivers"]["b"]["status"] == ELIMINATED


def test_sprints_add_to_maximum():
    s = make_season({"a": 100, "b": 70}, remaining=1)  # 95 < 100
    assert championship_status(s)["drivers"]["b"]["status"] == ELIMINATED
    s = make_season({"a": 100, "b": 70}, remaining=1, sprints_remaining=1)  # 70+25+8 = 103
    assert championship_status(s)["drivers"]["b"]["status"] == ALIVE
