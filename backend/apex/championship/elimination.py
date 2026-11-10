"""Engine A — exact mathematical championship eligibility.

Two questions are answered for every driver:

1. `mathematically_alive` — the official status. Is there ANY valid combination
   of remaining results (retirements included) in which this driver becomes
   champion? Because rivals can always fail to score (DNF), the optimal scenario
   for challenger *c* is: *c* wins every remaining Grand Prix and Sprint, and no
   rival scores more than their "cap". This reduces to a points bound plus an
   exact countback comparison, so it can never falsely eliminate a driver.

2. `alive_if_all_finish` — a stricter, more realistic question answered with
   constraint programming (OR-Tools CP-SAT): can *c* still win if every car in
   the field is classified, so that every points-paying position 2..10 in every
   remaining session must be handed to some rival? This captures "one race
   cannot have two winners"-type interactions between several rivals. When a
   driver is mathematically alive but not alive under this assumption, the UI
   explains that the title now requires rivals' retirements.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from ..domain import Season
from .scoring import Standing, standings

try:  # optional dependency
    from ortools.sat.python import cp_model  # type: ignore
except Exception:  # pragma: no cover
    cp_model = None

ALIVE, ELIMINATED, CLINCHED, CHAMPION = "ALIVE", "ELIMINATED", "CLINCHED", "CHAMPION"


@dataclass
class DriverStatus:
    driver_id: str
    status: str
    points: float
    max_points: float
    in_future_field: bool
    alive_if_all_finish: bool | None
    tie_break_uncertain: bool
    # Largest number of points each rival may still score for this driver to win
    # (only for alive drivers; drivers with no constraint omitted).
    rival_caps: dict[str, float]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _remaining(season: Season) -> tuple[int, int]:
    rem = season.remaining_sessions()
    return sum(1 for _, s in rem if s == "race"), sum(1 for _, s in rem if s == "sprint")


def future_field(season: Season) -> list[str]:
    """Drivers assumed to contest the remaining sessions: the latest round's
    participants (Engine D can override with confirmed entry lists)."""
    last = season.last_completed_round()
    if last == 0:
        return list(season.drivers)
    return list(season.entries_for_round(last))


def _caps_for(c: Standing, c_final: float, c_final_wins: int, table: list[Standing]) -> tuple[dict[str, float], bool, bool]:
    """Caps on each rival's future points so that `c` finishes ahead.
    Returns (caps, feasible, tie_uncertain)."""
    caps: dict[str, float] = {}
    tie_uncertain = False
    for j in table:
        if j.driver_id == c.driver_id:
            continue
        margin = c_final - j.points
        # At equal points, countback decides. In c's best case c wins every
        # remaining GP, so rival j cannot add wins.
        if c_final_wins > j.wins:
            cap = margin
        elif c_final_wins < j.wins:
            cap = margin - 0.5  # j must end strictly below (points move in >= 0.5 steps)
        else:
            cap = margin  # wins equal: deeper countback undecidable a priori -> conservative
            if margin >= 0:
                tie_uncertain = tie_uncertain or margin == 0
        if cap < 0:
            return caps, False, False
        caps[j.driver_id] = cap
    return caps, True, tie_uncertain


def _full_field_feasible(
    c_id: str, caps: dict[str, float], field: list[str], season: Season, time_limit: float = 3.0
) -> bool | None:
    """CP-SAT: assign every scoring position 2..N of every remaining session to
    distinct rivals in the field without exceeding any rival's cap."""
    rs = season.rules
    sessions = season.remaining_sessions()
    rivals = [d for d in field if d != c_id]
    slots: list[tuple[int, int, int]] = []  # (session_idx, position, points*2)
    for si, (_, kind) in enumerate(sessions):
        table = rs.sprint_points if kind == "sprint" else rs.race_points
        for pos in range(2, min(len(table), len(field)) + 1):  # every car classified
            slots.append((si, pos, int(round(table[pos - 1] * 2))))
    if not slots:
        return True
    n_sess = len(sessions)

    if cp_model is None:  # greedy witness search (sound if it succeeds)
        remaining = {d: caps.get(d, float("inf")) * 2 for d in rivals}
        used = {si: set() for si in range(n_sess)}
        for si, _, p2 in sorted(slots, key=lambda s: -s[2]):
            best = max((d for d in rivals if d not in used[si] and remaining[d] >= p2),
                       key=lambda d: remaining[d], default=None)
            if best is None:
                return None
            used[si].add(best)
            remaining[best] -= p2
        return True

    m = cp_model.CpModel()
    x = {}
    for k, (si, pos, p2) in enumerate(slots):
        for d in rivals:
            x[(k, d)] = m.NewBoolVar(f"x_{k}_{d}")
        m.AddExactlyOne(x[(k, d)] for d in rivals)
    for si in range(n_sess):
        ks = [k for k, s in enumerate(slots) if s[0] == si]
        for d in rivals:
            m.AddAtMostOne(x[(k, d)] for k in ks)
    for d in rivals:
        cap = caps.get(d)
        if cap is None:
            continue
        m.Add(sum(slots[k][2] * x[(k, d)] for k in range(len(slots))) <= int(cap * 2))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    res = solver.Solve(m)
    if res in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return True
    if res == cp_model.INFEASIBLE:
        return False
    return None


def championship_status(season: Season, field: list[str] | None = None, full_field_check: bool = True,
                        compute_clinch_round: bool = True) -> dict:
    rs = season.rules
    table = standings(season)
    field = field if field is not None else future_field(season)
    fset = set(field)
    n_gp, n_spr = _remaining(season)
    max_gain = n_gp * rs.max_race_points + n_spr * rs.max_sprint_points

    # Ensure drivers in the field with no results yet are represented.
    known = {s.driver_id for s in table}
    for d in field:
        if d not in known:
            table.append(Standing(d))

    out: dict[str, DriverStatus] = {}
    for c in table:
        in_field = c.driver_id in fset
        gain = max_gain if in_field else 0
        c_final = c.points + gain
        c_final_wins = c.wins + (n_gp if in_field else 0)
        caps, ok, tie_unc = _caps_for(c, c_final, c_final_wins, table)
        if not ok:
            out[c.driver_id] = DriverStatus(c.driver_id, ELIMINATED, c.points, c_final, in_field, False, False, {},
                                            "Cannot reach the leader's total even by winning every remaining session.")
            continue
        aff = None
        if full_field_check and (n_gp + n_spr) > 0 and in_field:
            binding = {d: v for d, v in caps.items() if d in fset and v < max_gain}
            aff = _full_field_feasible(c.driver_id, binding, field, season) if binding else True
        binding_caps = {d: v for d, v in caps.items() if d in fset and v < max_gain}
        out[c.driver_id] = DriverStatus(c.driver_id, ALIVE, c.points, c_final, in_field, aff, tie_unc,
                                        binding_caps, "")

    alive = [d for d, s in out.items() if s.status == ALIVE]
    season_over = (n_gp + n_spr) == 0
    champion = None
    if len(alive) == 1:
        champion = alive[0]
        out[champion].status = CHAMPION if season_over else CLINCHED
        out[champion].reason = ("Season complete." if season_over else
                                "No other driver can mathematically overtake the champion.")
    for d, s in out.items():
        if s.status == ALIVE and not s.reason:
            if s.alive_if_all_finish is False:
                s.reason = "Still mathematically possible, but only if title rivals fail to finish."
            else:
                s.reason = "Can still win the title on points."
    clinch_round = None
    if champion and compute_clinch_round:
        clinch_round = _clinch_round(season, champion)
    return {
        "remaining_grands_prix": n_gp,
        "remaining_sprints": n_spr,
        "max_points_available": max_gain,
        "clinched": champion is not None,
        "champion": champion,
        "clinch_round": clinch_round,
        "drivers": {d: s.to_dict() for d, s in out.items()},
    }


def _clinch_round(season: Season, champion: str) -> int | None:
    """Earliest round after which `champion` was mathematically confirmed."""
    for rnd in season.completed_rounds():
        sub = season.truncated(rnd)
        alive = [d for d, s in championship_status(sub, full_field_check=False, compute_clinch_round=False)["drivers"].items()
                 if s["status"] in (ALIVE, CLINCHED, CHAMPION)]
        if alive == [champion]:
            return rnd
    return None
