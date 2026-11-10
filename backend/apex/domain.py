"""Normalized, source-independent season model."""
from __future__ import annotations

from dataclasses import dataclass, field

from .rules import RuleSet, ruleset_for


@dataclass
class Driver:
    id: str  # stable internal id (see apex.grid.registry)
    code: str
    given_name: str
    family_name: str
    nationality: str = ""

    @property
    def name(self) -> str:
        return f"{self.given_name} {self.family_name}"


@dataclass
class Team:
    id: str
    name: str
    color: str = "#888888"


@dataclass
class Event:
    round: int
    name: str
    circuit_id: str
    country: str
    date: str
    has_sprint: bool
    status: str = "scheduled"  # scheduled | completed | cancelled
    sprint_completed: bool = False


@dataclass
class SessionResult:
    round: int
    session: str  # "race" | "sprint"
    driver_id: str
    team_id: str
    number: int | None
    grid: int | None
    position: int | None  # classified position, None if not classified
    position_text: str
    points: float
    status: str
    laps: int

    @property
    def classified(self) -> bool:
        return self.position is not None

    @property
    def finished(self) -> bool:
        """Took the chequered flag (on the lead lap or lapped). A driver can be
        *classified* after retiring late in the race; for performance modelling
        that is a reliability/incident event, not a pace signal."""
        st = (self.status or "").strip()
        return self.position is not None and (st in {"Finished", "Lapped", ""} or st.startswith("+"))

    @property
    def is_dnf(self) -> bool:
        """Non-finish for reliability purposes (retired, DNS, not classified).
        Disqualifications are excluded: they are not reliability failures."""
        return not self.finished and self.position_text != "D"


@dataclass
class Season:
    year: int
    drivers: dict[str, Driver]
    teams: dict[str, Team]
    events: list[Event]
    results: list[SessionResult]
    qualifying: dict[int, list[str]] = field(default_factory=dict)
    rules: RuleSet | None = None

    def __post_init__(self) -> None:
        if self.rules is None:
            self.rules = ruleset_for(self.year)
        self.events.sort(key=lambda e: e.round)

    # ----- convenience views -------------------------------------------------
    def completed_rounds(self) -> list[int]:
        done = {r.round for r in self.results if r.session == "race"}
        return sorted(done)

    def last_completed_round(self) -> int:
        rounds = self.completed_rounds()
        return rounds[-1] if rounds else 0

    def results_upto(self, rnd: int) -> list[SessionResult]:
        return [r for r in self.results if r.round <= rnd]

    def truncated(self, rnd: int) -> "Season":
        """The season as it was known after round `rnd` (no future information)."""
        return Season(
            year=self.year,
            drivers=self.drivers,
            teams=self.teams,
            events=[
                Event(e.round, e.name, e.circuit_id, e.country, e.date, e.has_sprint,
                      "completed" if e.round <= rnd else ("cancelled" if e.status == "cancelled" else "scheduled"),
                      e.round <= rnd and e.has_sprint)
                for e in self.events
            ],
            results=self.results_upto(rnd),
            qualifying={k: v for k, v in self.qualifying.items() if k <= rnd},
            rules=self.rules,
        )

    def remaining_sessions(self) -> list[tuple[int, str]]:
        """(round, session) for every future points-paying session, in order."""
        done = {(r.round, r.session) for r in self.results}
        out: list[tuple[int, str]] = []
        for e in self.events:
            if e.status == "cancelled":
                continue
            if e.has_sprint and (e.round, "sprint") not in done:
                out.append((e.round, "sprint"))
            if (e.round, "race") not in done:
                out.append((e.round, "race"))
        return out

    def entries_for_round(self, rnd: int) -> dict[str, str]:
        """driver_id -> team_id for drivers who took part in round `rnd`."""
        return {r.driver_id: r.team_id for r in self.results if r.round == rnd and r.session == "race"}
