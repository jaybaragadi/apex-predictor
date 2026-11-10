"""Reliability / non-finish risk.

P(DNF) per driver is an empirical-Bayes estimate: the driver's own recency-
weighted non-finish rate, shrunk toward their team's rate, which is shrunk
toward the league rate. A fraction of each team's risk is modelled as a
*shared* failure (common component, team-wide incident) so that teammates'
retirements are correlated in simulation.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..domain import Season


@dataclass
class ReliabilityModel:
    p_race: dict[str, float]
    p_team: dict[str, float]
    league: float
    shared_fraction: float = 0.25
    sprint_factor: float = 0.6  # sprints are shorter -> fewer failures


def fit_reliability(season: Season, upto: int, lam: float = 0.05, k_team: float = 12.0,
                    k_driver: float = 10.0, floor: float = 0.02) -> ReliabilityModel:
    w_tot, w_dnf = defaultdict(float), defaultdict(float)
    tw_tot, tw_dnf = defaultdict(float), defaultdict(float)
    team_of: dict[str, str] = {}
    lt = ld = 0.0
    for r in season.results:
        if r.round > upto or r.session != "race":
            continue
        w = 2.718281828 ** (-lam * (upto - r.round))
        dnf = 1.0 if r.is_dnf else 0.0
        w_tot[r.driver_id] += w
        w_dnf[r.driver_id] += w * dnf
        tw_tot[r.team_id] += w
        tw_dnf[r.team_id] += w * dnf
        lt += w
        ld += w * dnf
        team_of[r.driver_id] = r.team_id
    league = (ld + 1.0) / (lt + 10.0) if lt else 0.10
    p_team = {t: (tw_dnf[t] + k_team * league) / (tw_tot[t] + k_team) for t in tw_tot}
    p_race = {}
    for d in w_tot:
        pt = p_team.get(team_of[d], league)
        p_race[d] = max(floor, (w_dnf[d] + k_driver * pt) / (w_tot[d] + k_driver))
    return ReliabilityModel(p_race, p_team, league)
