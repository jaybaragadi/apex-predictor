import numpy as np
import pytest

from apex.championship.elimination import championship_status, future_field
from apex.championship.scoring import standings
from apex.models.performance import ModelConfig, fit_model
from apex.models.reliability import fit_reliability
from apex.simulation.monte_carlo import Condition, build_inputs, simulate


@pytest.fixture(scope="module")
def inputs_r14(season2026, circuits):
    sub = season2026.truncated(14)
    model = fit_model(sub, 14, circuits, ModelConfig())
    rel = fit_reliability(sub, 14)
    return sub, build_inputs(sub, standings(sub), model, rel, circuits, future_field(sub))


def test_probabilities_valid(inputs_r14):
    _, inp = inputs_r14
    r = simulate(inp, 20_000, seed=1)
    p = np.array(list(r.title.values()))
    assert np.all(p >= 0) and np.all(p <= 1)
    assert abs(p.sum() - 1) < 1e-9
    # position distribution rows and columns are proper distributions
    pd = np.array([r.position_dist[d] for d in inp.all_drivers])
    assert np.allclose(pd.sum(1), 1) and np.allclose(pd.sum(0), 1)


def test_eliminated_drivers_never_win(inputs_r14, season2026):
    sub, inp = inputs_r14
    st = championship_status(sub, full_field_check=False)
    r = simulate(inp, 20_000, seed=2)
    for d, s in st["drivers"].items():
        if s["status"] == "ELIMINATED":
            assert r.title.get(d, 0.0) == 0.0


def test_valid_finishing_orders_and_points_conservation(inputs_r14):
    _, inp = inputs_r14
    # one event, no DNFs -> each sim hands out exactly the full points table once
    inp1 = type(inp)(**{**inp.__dict__})
    inp1.events = inp.events[:1]
    inp1.theta = inp.theta[:1]
    inp1.dnf_race = np.zeros_like(inp.dnf_race)
    r = simulate(inp1, 5_000, seed=3)
    total_gain = sum(r.expected_points.values()) - inp.base_points.sum()
    assert total_gain == pytest.approx(sum(inp.events[0].points), rel=1e-9)
    stats = r.event_stats[0]["drivers"]
    assert sum(s["win"] for s in stats.values()) == pytest.approx(1.0)
    assert sum(s["podium"] for s in stats.values()) == pytest.approx(3.0)


def test_conditions_are_respected(inputs_r14):
    _, inp = inputs_r14
    nxt = inp.events[0]
    leader = inp.all_drivers[int(np.argmax(inp.base_points))]
    rival = "max_verstappen"
    r = simulate(inp, 5_000, seed=4,
                 conditions=[Condition(nxt.round, nxt.kind, positions={rival: 1}, dnf=[leader])])
    st = r.event_stats[0]["drivers"]
    assert st[rival]["win"] == 1.0
    assert st[leader]["dnf"] == 1.0 and st[leader]["exp_points"] == 0.0


def test_better_form_can_outrank_points_position(inputs_r14):
    """A driver behind on points can be the favourite if the model rates them
    faster: boost the 3rd-placed driver's strength and check the ranking flips."""
    _, inp = inputs_r14
    order = list(np.argsort(-inp.base_points))
    second, third = inp.all_drivers[order[1]], inp.all_drivers[order[2]]
    j3 = inp.field.index(third)
    j2 = inp.field.index(second)
    inp2 = type(inp)(**{**inp.__dict__})
    inp2.theta = inp.theta.copy()
    inp2.theta[:, j3] += 1.5
    inp2.theta[:, j2] -= 1.0
    r = simulate(inp2, 20_000, seed=5)
    assert r.title[third] > r.title[second]


def test_determinism_with_seed(inputs_r14):
    _, inp = inputs_r14
    a = simulate(inp, 5_000, seed=9).title
    b = simulate(inp, 5_000, seed=9).title
    assert a == b


def test_wet_race_increases_uncertainty(inputs_r14):
    _, inp = inputs_r14
    nxt = inp.events[0]
    dry = simulate(inp, 20_000, seed=6).event_stats[0]["drivers"]
    wet = simulate(inp, 20_000, seed=6, conditions=[Condition(nxt.round, nxt.kind, wet=True)]).event_stats[0]["drivers"]
    assert max(s["win"] for s in wet.values()) < max(s["win"] for s in dry.values())
