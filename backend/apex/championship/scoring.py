"""Championship standings from session results (Engine A, part 1)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..domain import Season, SessionResult
from .tie_breaks import countback_key

MAX_COUNTBACK = 25  # positions tracked for countback


@dataclass
class Standing:
    driver_id: str
    points: float = 0.0
    # finishes[k] = number of Grand Prix finishes in position k+1 (countback)
    finishes: list[int] = field(default_factory=lambda: [0] * MAX_COUNTBACK)
    best_qualifying: list[int] = field(default_factory=lambda: [0] * MAX_COUNTBACK)
    position: int = 0
    team_id: str = ""

    @property
    def wins(self) -> int:
        return self.finishes[0]


def standings(season: Season, upto_round: int | None = None) -> list[Standing]:
    """Ordered standings. Uses the official points on each result (which already
    encode penalties, DSQs and shortened-race scales) — see `validate_points` for
    the cross-check against the ruleset."""
    rs = season.rules
    table: dict[str, Standing] = {}
    for r in season.results:
        if upto_round is not None and r.round > upto_round:
            continue
        st = table.setdefault(r.driver_id, Standing(r.driver_id))
        st.points += r.points
        st.team_id = r.team_id
        counts_for_countback = r.session == "race" or rs.countback_includes_sprints
        if counts_for_countback and r.position is not None and r.position <= MAX_COUNTBACK:
            st.finishes[r.position - 1] += 1
    for rnd, order in season.qualifying.items():
        if upto_round is not None and rnd > upto_round:
            continue
        for i, d in enumerate(order[:MAX_COUNTBACK]):
            if d in table:
                table[d].best_qualifying[i] += 1
    ordered = sorted(table.values(), key=countback_key, reverse=True)
    for i, st in enumerate(ordered, 1):
        st.position = i
    return ordered


def validate_points(season: Season, tolerance: float = 1e-6) -> list[str]:
    """Recompute points from classified positions using the season's ruleset and
    report any disagreement with the official points. Disagreements are expected
    for shortened races / penalties and are surfaced for review, never silently
    overwritten."""
    issues: list[str] = []
    for r in season.results:
        expected = season.rules.points_for(r.session, r.position)
        if r.position_text == "D":
            expected = 0
        if abs(expected - r.points) > tolerance:
            issues.append(
                f"R{r.round} {r.session} {r.driver_id}: official {r.points} vs rules {expected} "
                f"(pos {r.position_text})"
            )
    return issues


def points_by_round(season: Season) -> dict[str, list[float]]:
    """Cumulative points per driver after each completed round (for charts)."""
    rounds = season.completed_rounds()
    per: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for r in season.results:
        per[r.driver_id][r.round] += r.points
    out: dict[str, list[float]] = {}
    for d, m in per.items():
        acc, series = 0.0, []
        for rnd in rounds:
            acc += m.get(rnd, 0.0)
            series.append(acc)
        out[d] = series
    return out
