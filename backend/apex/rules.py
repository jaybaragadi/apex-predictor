"""Versioned, season-specific championship regulations.

Every scoring rule lives here as *data*. A new season with unchanged rules needs
no code change: `ruleset_for(year)` returns the latest ruleset whose range covers
it. When the FIA publishes new rules, add a new RuleSet entry (and have a human
verify it against the published Sporting Regulations before activating it).
"""
from __future__ import annotations

from dataclasses import dataclass, field

FULL_GP_2010 = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)


@dataclass(frozen=True)
class ShortenedBand:
    """Points for a race whose completed distance is <= `max_fraction` of scheduled."""

    max_fraction: float
    points: tuple[int, ...]


@dataclass(frozen=True)
class RuleSet:
    version: str
    first_season: int
    last_season: int | None
    race_points: tuple[int, ...]
    sprint_points: tuple[int, ...] = ()
    fastest_lap_point: bool = False  # +1 for fastest lap if classified in top 10
    # Bands are checked in order; the first band whose max_fraction >= distance wins.
    # Distance above the last band => full points.
    shortened_race_bands: tuple[ShortenedBand, ...] = ()
    min_laps_for_any_points: int = 2
    sprint_min_fraction: float = 0.5
    countback_includes_sprints: bool = False
    verified: bool = True
    notes: str = ""

    @property
    def max_race_points(self) -> int:
        return self.race_points[0] + (1 if self.fastest_lap_point else 0)

    @property
    def max_sprint_points(self) -> int:
        return self.sprint_points[0] if self.sprint_points else 0

    def points_for(
        self,
        session: str,
        position: int | None,
        *,
        distance_fraction: float = 1.0,
        leader_laps: int | None = None,
        fastest_lap: bool = False,
    ) -> float:
        """Points for a classified `position` (1-based). `None` = not classified."""
        if position is None or position < 1:
            return 0
        if session == "sprint":
            if distance_fraction < self.sprint_min_fraction:
                return 0
            tbl = self.sprint_points
            return tbl[position - 1] if position <= len(tbl) else 0
        # Grand Prix
        if leader_laps is not None and leader_laps < self.min_laps_for_any_points:
            return 0
        tbl = self.race_points
        if distance_fraction < 1.0:
            for band in self.shortened_race_bands:
                if distance_fraction <= band.max_fraction:
                    tbl = band.points
                    break
        pts = tbl[position - 1] if position <= len(tbl) else 0
        if fastest_lap and self.fastest_lap_point and position <= 10 and tbl is self.race_points:
            pts += 1
        return pts


# Reduced-points schedule introduced for 2022 and carried into later seasons.
# Verify against the current FIA Sporting Regulations before each season.
SHORTENED_2022 = (
    ShortenedBand(0.25, (6, 4, 3, 2, 1)),
    ShortenedBand(0.50, (13, 10, 8, 6, 5, 4, 3, 2, 1)),
    ShortenedBand(0.75, (19, 14, 12, 9, 8, 6, 5, 3, 2, 1)),
)

RULESETS: tuple[RuleSet, ...] = (
    RuleSet("1991", 1991, 2002, (10, 6, 4, 3, 2, 1),
            shortened_race_bands=(ShortenedBand(0.75, (5, 3, 2, 1.5, 1, 0.5)),)),
    RuleSet("2003", 2003, 2009, (10, 8, 6, 5, 4, 3, 2, 1),
            shortened_race_bands=(ShortenedBand(0.75, (5, 4, 3, 2.5, 2, 1.5, 1, 0.5)),)),
    RuleSet("2010", 2010, 2018, FULL_GP_2010,
            shortened_race_bands=(ShortenedBand(0.75, tuple(p / 2 for p in FULL_GP_2010)),)),
    RuleSet("2019", 2019, 2020, FULL_GP_2010, fastest_lap_point=True,
            shortened_race_bands=(ShortenedBand(0.75, tuple(p / 2 for p in FULL_GP_2010)),)),
    RuleSet("2021", 2021, 2021, FULL_GP_2010, sprint_points=(3, 2, 1), fastest_lap_point=True,
            shortened_race_bands=(ShortenedBand(0.75, tuple(p / 2 for p in FULL_GP_2010)),)),
    RuleSet("2022", 2022, 2024, FULL_GP_2010, sprint_points=(8, 7, 6, 5, 4, 3, 2, 1),
            fastest_lap_point=True, shortened_race_bands=SHORTENED_2022),
    RuleSet("2025", 2025, None, FULL_GP_2010, sprint_points=(8, 7, 6, 5, 4, 3, 2, 1),
            fastest_lap_point=False, shortened_race_bands=SHORTENED_2022,
            notes="Fastest-lap bonus abolished from 2025. 2026 uses the same points tables."),
)

# Seasons with a major technical-regulation reset: older car performance is
# heavily discounted when forming a preseason prior.
MAJOR_REG_CHANGE_SEASONS = frozenset({2009, 2014, 2017, 2022, 2026})


def ruleset_for(season: int) -> RuleSet:
    for rs in reversed(RULESETS):
        if season >= rs.first_season and (rs.last_season is None or season <= rs.last_season):
            return rs
    raise KeyError(f"No championship ruleset configured for {season}; add one to apex/rules.py")
