import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apex.domain import Driver, Event, Season, SessionResult, Team  # noqa: E402
from apex.ingestion.normalize import load_circuits, load_seed  # noqa: E402


@pytest.fixture(scope="session")
def season2026():
    return load_seed(2026)


@pytest.fixture(scope="session")
def circuits():
    return load_circuits()


def make_season(points: dict[str, float], remaining: int, *, field_size: int | None = None, wins: dict | None = None,
                sprints_remaining: int = 0, year: int = 2026) -> Season:
    """Synthetic season: one completed round that produces `points`, plus
    `remaining` scheduled Grands Prix."""
    ids = list(points)
    extra = [f"x{i}" for i in range(max(0, (field_size or len(ids)) - len(ids)))]
    drivers = {d: Driver(d, d[:3].upper(), d, d) for d in ids + extra}
    teams = {"t": Team("t", "T")}
    results = []
    wins = wins or {}
    for i, d in enumerate(ids + extra):
        results.append(SessionResult(1, "race", d, "t", i + 1, i + 1, i + 1, str(i + 1), points.get(d, 0.0), "Finished", 50))
        for w in range(wins.get(d, 0)):  # extra historical wins via synthetic earlier rounds is overkill:
            pass
    events = [Event(1, "R1", "c", "", "2026-01-01", False, "completed")]
    for r in range(2, 2 + remaining):
        events.append(Event(r, f"R{r}", "c", "", f"2026-0{min(r,9)}-01", r - 2 < sprints_remaining))
    s = Season(year, drivers, teams, events, results)
    return s
