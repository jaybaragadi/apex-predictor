"""Engine C — Monte Carlo championship simulator.

Every simulated season draws a *complete, valid finishing order* for every
remaining Sprint and Grand Prix (Plackett–Luce sampling via the Gumbel-max
trick), never independent positions per driver. Per simulation:

1. Parameter uncertainty: each driver's strength is perturbed once by its
   posterior standard deviation (rookies / new teams vary more).
2. Per event: a shared team shock (teammates move together), circuit-type
   fit, and race noise. Wet conditions raise the noise temperature.
3. Reliability: correlated team-level + individual non-finishes.
4. Points from the season's ruleset; championship resolved by points and
   then FIA countback (wins, 2nds, 3rds).
Conditioned scenarios fix chosen positions / retirements and sample the rest.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..championship.scoring import Standing
from ..domain import Season
from ..models.performance import PerformanceModel
from ..models.reliability import ReliabilityModel


@dataclass
class SimEvent:
    round: int
    kind: str  # race | sprint
    name: str
    ctype: str
    points: tuple
    wet: bool = False


@dataclass
class SimInputs:
    """Plain arrays — also exported to the frontend so the browser can run
    identical What-If simulations."""
    all_drivers: list[str]
    base_points: np.ndarray
    base_wins: np.ndarray
    base_p2: np.ndarray
    base_p3: np.ndarray
    field: list[str]  # drivers contesting remaining events (subset of all_drivers)
    field_team: list[str]
    theta: np.ndarray  # (E, F) per-event mean strength
    theta_sd: np.ndarray  # (F,)
    team_shock_sd: float
    dnf_race: np.ndarray  # (F,)
    shared_fraction: float
    sprint_factor: float
    events: list[SimEvent]

    def to_json(self) -> dict:
        return {
            "all_drivers": self.all_drivers,
            "base_points": self.base_points.tolist(), "base_wins": self.base_wins.tolist(),
            "base_p2": self.base_p2.tolist(), "base_p3": self.base_p3.tolist(),
            "field": self.field, "field_team": self.field_team,
            "theta": np.round(self.theta, 4).tolist(), "theta_sd": np.round(self.theta_sd, 4).tolist(),
            "team_shock_sd": self.team_shock_sd, "dnf_race": np.round(self.dnf_race, 4).tolist(),
            "shared_fraction": self.shared_fraction, "sprint_factor": self.sprint_factor,
            "events": [e.__dict__ for e in self.events],
        }


@dataclass
class Condition:
    """Fixed outcome for one remaining session."""
    round: int
    kind: str = "race"
    positions: dict[str, int] = field(default_factory=dict)  # driver -> 1-based position
    dnf: list[str] = field(default_factory=list)
    wet: bool | None = None


@dataclass
class SimResult:
    n_sims: int
    title: dict[str, float]
    position_dist: dict[str, list[float]]
    expected_points: dict[str, float]
    event_stats: list[dict]
    head_to_head: dict[str, dict[str, float]]
    title_if_wins_next_gp: dict[str, float] = field(default_factory=dict)


def build_inputs(season: Season, table: list[Standing], model: PerformanceModel, rel: ReliabilityModel,
                 circuits: dict, field: list[str]) -> SimInputs:
    rs = season.rules
    all_drivers = [s.driver_id for s in table]
    for d in field:
        if d not in all_drivers:
            all_drivers.append(d)
    st = {s.driver_id: s for s in table}
    g = lambda d, f: getattr(st[d], f) if d in st else 0
    base_points = np.array([float(g(d, "points")) for d in all_drivers])
    base_wins = np.array([st[d].finishes[0] if d in st else 0 for d in all_drivers])
    base_p2 = np.array([st[d].finishes[1] if d in st else 0 for d in all_drivers])
    base_p3 = np.array([st[d].finishes[2] if d in st else 0 for d in all_drivers])
    ev_by_round = {e.round: e for e in season.events}
    events = []
    for rnd, kind in season.remaining_sessions():
        e = ev_by_round[rnd]
        ctype = circuits.get(e.circuit_id, {}).get("type", "balanced")
        events.append(SimEvent(rnd, kind, e.name, ctype, rs.sprint_points if kind == "sprint" else rs.race_points))
    field_team = [model.current_team.get(d, "") for d in field]
    theta = np.zeros((len(events), len(field)))
    sd = np.zeros(len(field))
    for j, d in enumerate(field):
        for e_i, ev in enumerate(events):
            theta[e_i, j], sd[j] = model.strength(d, field_team[j], ev.ctype)
        if not events:
            _, sd[j] = model.strength(d, field_team[j])
    dnf = np.array([rel.p_race.get(d, rel.p_team.get(field_team[j], rel.league)) for j, d in enumerate(field)])
    return SimInputs(all_drivers, base_points, base_wins, base_p2, base_p3, field, field_team, theta, sd,
                     model.cfg.team_shock_sd, dnf, rel.shared_fraction, rel.sprint_factor, events)


def simulate(inp: SimInputs, n_sims: int = 100_000, seed: int = 2026, conditions: list[Condition] | None = None,
             chunk: int = 25_000, wet_temperature: float = 1.6, h2h_top: int = 8) -> SimResult:
    rng = np.random.default_rng(seed)
    A, F, E = len(inp.all_drivers), len(inp.field), len(inp.events)
    a_idx = {d: i for i, d in enumerate(inp.all_drivers)}
    f_to_a = np.array([a_idx[d] for d in inp.field], dtype=int)
    f_idx = {d: i for i, d in enumerate(inp.field)}
    teams = sorted(set(inp.field_team))
    t_of = np.array([teams.index(t) for t in inp.field_team], dtype=int) if F else np.zeros(0, int)
    T = len(teams)
    cond = {(c.round, c.kind): c for c in (conditions or [])}

    # Team shared-failure probability q_T and residual individual probability.
    q_team = np.zeros(T)
    for k in range(T):
        members = inp.dnf_race[t_of == k]
        q_team[k] = inp.shared_fraction * members.min() if len(members) else 0.0

    title = np.zeros(A)
    pos_counts = np.zeros((A, A))
    exp_pts = np.zeros(A)
    ev_win = np.zeros((E, F)); ev_pod = np.zeros((E, F)); ev_pts = np.zeros((E, F)); ev_pos = np.zeros((E, F))
    ev_dnf = np.zeros((E, F))
    ev_fpos = np.zeros((E, F)); ev_fpos2 = np.zeros((E, F)); ev_fin = np.zeros((E, F))
    first_race = next((i for i, ev in enumerate(inp.events) if ev.kind == "race"), None)
    joint = np.zeros((F, A))  # winner of next GP x champion
    top = list(np.argsort(-inp.base_points)[:h2h_top])
    h2h = np.zeros((len(top), len(top)))

    done = 0
    while done < n_sims:
        S = min(chunk, n_sims - done)
        pts = np.tile(inp.base_points, (S, 1))
        wins = np.tile(inp.base_wins.astype(float), (S, 1))
        p2 = np.tile(inp.base_p2.astype(float), (S, 1))
        p3 = np.tile(inp.base_p3.astype(float), (S, 1))
        first_winner = None
        if F and E:
            z = rng.standard_normal((S, F)) * inp.theta_sd
            for e_i, ev in enumerate(inp.events):
                c = cond.get((ev.round, ev.kind))
                wet = c.wet if (c and c.wet is not None) else ev.wet
                temp = wet_temperature if wet else 1.0
                shock = rng.standard_normal((S, T)) * inp.team_shock_sd
                th = inp.theta[e_i] + z + shock[:, t_of]
                gum = rng.gumbel(size=(S, F))
                score = th / temp + gum
                factor = (inp.sprint_factor if ev.kind == "sprint" else 1.0) * (1.4 if wet else 1.0)
                p_ind = np.clip((inp.dnf_race * factor - q_team[t_of] * factor) / np.maximum(1 - q_team[t_of] * factor, 1e-9), 0, 1)
                team_fail = rng.random((S, T)) < q_team * factor
                dnf = (rng.random((S, F)) < p_ind) | team_fail[:, t_of]
                fixed_pos = np.full(F, -1)
                if c:
                    for d, p in c.positions.items():
                        if d in f_idx:
                            fixed_pos[f_idx[d]] = p - 1
                    for d in c.dnf:
                        if d in f_idx:
                            dnf[:, f_idx[d]] = True
                    dnf[:, fixed_pos >= 0] = False
                key = np.where(dnf, -1e6 + gum, score)
                is_fixed = fixed_pos >= 0
                key[:, is_fixed] = -np.inf
                rank = np.argsort(np.argsort(-key, axis=1, kind="stable"), axis=1)
                free_positions = np.array([p for p in range(F) if p not in set(fixed_pos[is_fixed].tolist())])
                n_free = F - is_fixed.sum()
                pos = np.empty((S, F), dtype=int)
                pos[:, ~is_fixed] = free_positions[np.minimum(rank[:, ~is_fixed], n_free - 1)]
                pos[:, is_fixed] = fixed_pos[is_fixed]
                table = np.array(list(ev.points) + [0] * max(0, F - len(ev.points)))[:F]
                gained = np.where(dnf, 0.0, table[pos])
                pts[:, f_to_a] += gained
                if ev.kind == "race":
                    wins[:, f_to_a] += (pos == 0) & ~dnf
                    p2[:, f_to_a] += (pos == 1) & ~dnf
                    p3[:, f_to_a] += (pos == 2) & ~dnf
                ev_win[e_i] += ((pos == 0) & ~dnf).sum(0)
                ev_pod[e_i] += ((pos <= 2) & ~dnf).sum(0)
                ev_pts[e_i] += gained.sum(0)
                ev_pos[e_i] += (pos + 1).sum(0)
                ev_dnf[e_i] += dnf.sum(0)
                fin = ~dnf
                ev_fpos[e_i] += np.where(fin, pos + 1, 0).sum(0)
                ev_fpos2[e_i] += np.where(fin, (pos + 1) ** 2, 0).sum(0)
                ev_fin[e_i] += fin.sum(0)
                if e_i == first_race:
                    w = (pos == 0) & fin
                    first_winner = np.where(w.any(1), w.argmax(1), -1)
        key = pts * 1e6 + wins * 1e4 + p2 * 1e2 + p3
        order = np.argsort(-key, axis=1, kind="stable")
        title += np.bincount(order[:, 0], minlength=A)
        if first_winner is not None:
            ok = first_winner >= 0
            np.add.at(joint, (first_winner[ok], order[ok, 0]), 1)
        rank = np.empty_like(order)
        rank[np.arange(S)[:, None], order] = np.arange(A)[None, :]
        pos_counts += np.bincount((np.arange(A)[None, :] * A + rank).ravel(), minlength=A * A).reshape(A, A)
        exp_pts += pts.sum(0)
        for a, i in enumerate(top):
            for b, j in enumerate(top):
                if a != b:
                    h2h[a, b] += (rank[:, i] < rank[:, j]).sum()
        done += S

    n = float(n_sims)
    ids = inp.all_drivers
    event_stats = []
    for e_i, ev in enumerate(inp.events):
        event_stats.append({
            "round": ev.round, "kind": ev.kind, "name": ev.name,
            "drivers": {d: {"win": ev_win[e_i, j] / n, "podium": ev_pod[e_i, j] / n,
                            "exp_points": ev_pts[e_i, j] / n, "exp_position": ev_pos[e_i, j] / n,
                            "dnf": ev_dnf[e_i, j] / n,
                            "finish_position": ev_fpos[e_i, j] / max(ev_fin[e_i, j], 1),
                            "finish_position_sd": float(np.sqrt(max(ev_fpos2[e_i, j] / max(ev_fin[e_i, j], 1) - (ev_fpos[e_i, j] / max(ev_fin[e_i, j], 1)) ** 2, 0)))}
                        for j, d in enumerate(inp.field)},
        })
    return SimResult(
        n_sims=n_sims,
        title={d: title[i] / n for i, d in enumerate(ids)},
        position_dist={d: (pos_counts[i] / n).tolist() for i, d in enumerate(ids)},
        expected_points={d: exp_pts[i] / n for i, d in enumerate(ids)},
        event_stats=event_stats,
        title_if_wins_next_gp={d: float(joint[j, a_idx[d]] / joint[j].sum()) for j, d in enumerate(inp.field) if joint[j].sum() > 0},
        head_to_head={ids[i]: {ids[j]: h2h[a, b] / n for b, j in enumerate(top) if a != b} for a, i in enumerate(top)},
    )
