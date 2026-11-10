"""Turn raw source records (seed CSVs or Jolpica JSON) into a `Season`.

All sources are normalized into the same flat record shape first, then
corrections are applied, then identities are resolved through the registry.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..domain import Driver, Event, Season, SessionResult, Team

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def result_from_record(rec: dict, session: str) -> SessionResult:
    pt = str(rec["position_text"])
    pos = _int(pt)  # "R" (retired), "W" (withdrawn/DNS), "D" (DSQ), "N" (not classified) -> None
    return SessionResult(
        round=int(rec["round"]), session=session, driver_id=rec["driver"], team_id=rec["team"],
        number=_int(rec.get("number")), grid=_int(rec.get("grid")), position=pos, position_text=pt,
        points=float(rec.get("points") or 0), status=rec.get("status", ""), laps=_int(rec.get("laps")) or 0,
    )


def apply_corrections(records: list[dict], corrections: list[dict], session: str) -> list[dict]:
    """Controlled manual corrections (e.g. post-race penalties confirmed by the
    FIA but not yet reflected in an API). Each correction is explicit and logged."""
    for c in corrections:
        if c.get("session", "race") != session:
            continue
        for rec in records:
            if int(rec["round"]) == int(c["round"]) and rec["driver"] == c["driver"]:
                rec.update(c["set"])
    return records


def load_corrections(year: int) -> list[dict]:
    p = DATA_DIR / "corrections" / f"{year}.json"
    return json.loads(p.read_text()) if p.exists() else []


def build_season(year: int, *, calendar: list[dict], drivers: list[dict], teams: list[dict],
                 race_records: list[dict], sprint_records: list[dict], qualifying: dict[int, list[str]]) -> Season:
    corr = load_corrections(year)
    race_records = apply_corrections(race_records, corr, "race")
    sprint_records = apply_corrections(sprint_records, corr, "sprint")
    dmap = {}
    for d in drivers:
        code = d.get("code") or d["family_name"][:3].upper()
        dmap[d["source_id"]] = Driver(d["source_id"], code, d["given_name"], d["family_name"], d.get("nationality", ""))
    tmap = {t["source_id"]: Team(t["source_id"], t["name"], t.get("color") or "#888888") for t in teams}
    results = [result_from_record(r, "race") for r in race_records] + [result_from_record(r, "sprint") for r in sprint_records]
    for r in results:  # tolerate drivers/teams discovered only through results
        dmap.setdefault(r.driver_id, Driver(r.driver_id, r.driver_id[:3].upper(), "", r.driver_id.replace("_", " ").title()))
        tmap.setdefault(r.team_id, Team(r.team_id, r.team_id.replace("_", " ").title()))
    events = [
        Event(int(c["round"]), c["name"], c["circuit_id"], c.get("country", ""), c["date"], bool(c.get("sprint_date")),
              c.get("status") or "scheduled")
        for c in calendar
    ]
    done = {r.round for r in results if r.session == "race"}
    for e in events:
        if e.round in done:
            e.status = "completed"
    return Season(year, dmap, tmap, events, results, qualifying)


def load_seed(year: int, seed_dir: Path | None = None) -> Season:
    d = seed_dir or (DATA_DIR / "seed" / str(year))
    read = lambda name: list(csv.DictReader(open(d / name, encoding="utf-8")))
    quali: dict[int, list[str]] = {}
    qp = d / "qualifying.txt"
    if qp.exists():
        for line in qp.read_text().splitlines():
            if ":" in line:
                rnd, order = line.split(":", 1)
                quali[int(rnd)] = order.split()
    sprint = read("sprint.csv") if (d / "sprint.csv").exists() else []
    return build_season(year, calendar=read("calendar.csv"), drivers=read("drivers.csv"), teams=read("teams.csv"),
                        race_records=read("results.csv"), sprint_records=sprint, qualifying=quali)


def load_circuits() -> dict[str, dict]:
    p = DATA_DIR / "circuits.json"
    return json.loads(p.read_text()) if p.exists() else {}
