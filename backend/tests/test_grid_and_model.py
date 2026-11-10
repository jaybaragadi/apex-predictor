import numpy as np

from apex.grid.registry import Registry
from apex.grid.sync import sync_season
from apex.models.performance import ModelConfig, _fit_once, fit_model


def test_number_change_keeps_identity(tmp_path):
    reg = Registry()
    a = reg.resolve_driver("jolpica", "max_verstappen", "Max Verstappen", "VER", 2025, 33)
    b = reg.resolve_driver("jolpica", "max_verstappen", "Max Verstappen", "VER", 2026, 3)
    assert a == b
    assert reg.drivers[a]["numbers"] == {"2025": 33, "2026": 3}
    assert any(c["type"] == "number_change" and c["old"] == 33 and c["new"] == 3 for c in reg.change_log)
    reg.save(tmp_path / "r.json")
    reg2 = Registry.load(tmp_path / "r.json")
    assert reg2.resolve_driver("jolpica", "max_verstappen", "Max Verstappen") == a


def test_team_rename_is_alias_not_new_team():
    reg = Registry()
    t1 = reg.resolve_team("jolpica", "sauber", "Sauber", 2025)
    t2 = reg.resolve_team("jolpica", "sauber", "Audi", 2026)
    assert t1 == t2 and reg.teams[t1]["aliases"] == ["Sauber", "Audi"]
    assert any(c["type"] == "team_renamed" for c in reg.change_log)


def test_new_team_and_team_switch_detected(season2026):
    reg = Registry()
    s, changes = sync_season(season2026, reg)
    kinds = {c["type"] for c in changes}
    assert "new_team" in kinds and "new_driver" in kinds
    # Lawson moved Racing Bulls -> Red Bull at round 12 and back later
    switches = [c for c in changes if c["type"] == "team_switch" and c["driver"] == "drv_lawson"]
    assert {c["round"] for c in switches} >= {12}
    assert "drv_antonelli" in s.drivers


def test_ambiguous_name_goes_to_review_queue():
    reg = Registry()
    reg.resolve_driver("jolpica", "smith", "John Smith")
    reg.resolve_driver("jolpica", "smith_2", "John Smith")
    assert reg.review_queue and reg.review_queue[0]["type"] == "possible_duplicate_driver"
    assert len(reg.drivers) == 2  # not merged automatically


def test_future_field_prefers_confirmed_entries():
    reg = Registry()
    for d in ["a", "b"]:
        reg.record_participation(2026, 5, d, "t", 1)
    drivers, notes = reg.future_field(2026, 6)
    assert set(drivers) == {"a", "b"} and notes[0]["type"] == "assumed_from_last_round"
    drivers, notes = reg.future_field(2026, 6, [{"round": 6, "drivers": ["a", "c"], "status": "confirmed"}])
    assert drivers == ["a", "c"]
    drivers, _ = reg.future_field(2026, 6, [{"round": 6, "drivers": ["a", "rumour"], "status": "announced"}])
    assert set(drivers) == {"a", "b"}  # rumours/announcements don't change the simulated grid


def test_pl_gradient_matches_numerical():
    cfg = ModelConfig()
    obs = [(1, "race", ["a", "b", "c", "d"], ["t1", "t1", "t2", "t2"], "balanced", 1.0),
           (2, "race", ["c", "a", "d", "b"], ["t2", "t1", "t2", "t1"], "power", 1.0)]
    fit = _fit_once(obs, ["a", "b", "c", "d"], ["t1", "t2"], ["balanced", "power"], 2, 0.1, cfg)
    # optimum: driver who beat everyone more often rates higher
    assert fit.d[0] > fit.d[1]


def test_driver_transfer_rebases_on_new_car(season2026, circuits):
    m = fit_model(season2026, 20, circuits, ModelConfig())
    mu_rb, _ = m.strength("lawson", "rb")
    mu_redbull, _ = m.strength("lawson", "red_bull")
    ts = m.team_strength()
    assert (mu_redbull > mu_rb) == (ts["red_bull"] > ts["rb"])


def test_rookie_or_unknown_driver_has_wider_uncertainty(season2026, circuits):
    m = fit_model(season2026, 20, circuits, ModelConfig())
    _, sd_known = m.strength("hamilton")
    _, sd_new = m.strength("brand_new_rookie", "ferrari")
    assert sd_new > sd_known


def test_incidents_are_detected(season2026, circuits):
    m = fit_model(season2026, 20, circuits, ModelConfig())
    assert any(i["driver"] == "antonelli" and i["round"] == 9 for i in m.meta["incidents"])
