"""Jolpica (Ergast-compatible) client with caching, rate limiting, retries and
validation against the official standings endpoint.

Documented unauthenticated limits: 4 requests/second, 500/hour. Responses are
cached on disk; completed rounds are immutable unless an amendment is
detected, so steady-state polling costs only a handful of requests.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from ..domain import Season
from .normalize import DATA_DIR, build_season

BASE = "https://api.jolpi.ca/ergast/f1"
CACHE = DATA_DIR / "cache" / "jolpica"
log = logging.getLogger("apex.jolpica")


class RateLimiter:
    def __init__(self, per_second: float = 3.0, per_hour: int = 450):
        self.min_gap = 1.0 / per_second
        self.per_hour = per_hour
        self.calls: list[float] = []

    def wait(self) -> None:
        now = time.monotonic()
        self.calls = [t for t in self.calls if now - t < 3600]
        if len(self.calls) >= self.per_hour:
            raise RuntimeError("hourly request budget exhausted; retry later")
        if self.calls and now - self.calls[-1] < self.min_gap:
            time.sleep(self.min_gap - (now - self.calls[-1]))
        self.calls.append(time.monotonic())


class JolpicaClient:
    def __init__(self, cache_dir: Path = CACHE, max_age: float = 600, client: httpx.Client | None = None):
        self.cache_dir = cache_dir
        self.max_age = max_age
        self.http = client or httpx.Client(timeout=20, headers={"User-Agent": "apex-predictor/1.0"})
        self.limiter = RateLimiter()

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")

    def get(self, path: str, *, params: dict | None = None, max_age: float | None = None) -> dict:
        url = f"{BASE}/{path.strip('/')}/"
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cp = self._cache_path(url)
        age = max_age if max_age is not None else self.max_age
        if cp.exists() and time.time() - cp.stat().st_mtime < age:
            return json.loads(cp.read_text())
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                self.limiter.wait()
                r = self.http.get(url)
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                r.raise_for_status()
                data = r.json()
                cp.parent.mkdir(parents=True, exist_ok=True)
                cp.write_text(json.dumps(data))
                return data
            except Exception as exc:  # retry with exponential backoff
                last_exc = exc
                time.sleep(min(2 ** attempt, 30))
        if cp.exists():  # serve stale cache rather than fail
            log.warning("serving stale cache for %s after error: %s", url, last_exc)
            return json.loads(cp.read_text())
        raise RuntimeError(f"failed to fetch {url}: {last_exc}")

    def paged(self, path: str, key: str) -> list[tuple[dict, dict]]:
        out, offset, total = [], 0, 1
        while offset < total:
            j = self.get(path, params={"limit": 100, "offset": offset})
            mr = j["MRData"]
            total = int(mr["total"])
            for race in mr["RaceTable"]["Races"]:
                for row in race.get(key, []):
                    out.append((race, row))
            offset += 100
        return out


def _rec(race: dict, row: dict) -> dict:
    return {"round": int(race["round"]), "driver": row["Driver"]["driverId"], "team": row["Constructor"]["constructorId"],
            "number": row.get("number"), "grid": row.get("grid"), "position_text": row.get("positionText"),
            "points": row.get("points", 0), "status": row.get("status", ""), "laps": row.get("laps", 0)}


def fetch_season(year: int, client: JolpicaClient | None = None) -> Season:
    c = client or JolpicaClient()
    races = c.get(f"{year}/races", params={"limit": 100}, max_age=3600)["MRData"]["RaceTable"]["Races"]
    calendar = [{"round": r["round"], "name": r["raceName"], "circuit_id": r["Circuit"]["circuitId"],
                 "country": r["Circuit"]["Location"].get("country", ""), "date": r["date"],
                 "sprint_date": (r.get("Sprint") or {}).get("date", ""), "status": "scheduled"} for r in races]
    res = c.paged(f"{year}/results", "Results")
    spr = c.paged(f"{year}/sprint", "SprintResults")
    qual = c.paged(f"{year}/qualifying", "QualifyingResults")
    drivers_raw = c.get(f"{year}/drivers", params={"limit": 100}, max_age=3600)["MRData"]["DriverTable"]["Drivers"]
    drivers = [{"source_id": d["driverId"], "code": d.get("code", ""), "given_name": d["givenName"],
                "family_name": d["familyName"], "permanent_number": d.get("permanentNumber", ""),
                "nationality": d.get("nationality", "")} for d in drivers_raw]
    teams_seen = {}
    for race, row in res + spr:
        teams_seen[row["Constructor"]["constructorId"]] = row["Constructor"]["name"]
    colors = _team_colors(year)
    teams = [{"source_id": t, "name": n, "color": colors.get(t, "")} for t, n in teams_seen.items()]
    # Only drivers who actually took part are part of the season model.
    took_part = {row["Driver"]["driverId"] for _, row in res + spr}
    drivers = [d for d in drivers if d["source_id"] in took_part]
    quali: dict[int, list[str]] = {}
    for race, row in sorted(qual, key=lambda x: (int(x[0]["round"]), int(x[1]["position"]))):
        quali.setdefault(int(race["round"]), []).append(row["Driver"]["driverId"])
    season = build_season(year, calendar=calendar, drivers=drivers, teams=teams,
                          race_records=[_rec(r, x) for r, x in res], sprint_records=[_rec(r, x) for r, x in spr],
                          qualifying=quali)
    validate_against_official(season, c)
    return season


def _team_colors(year: int) -> dict[str, str]:
    """Team colours: seed file first; OpenF1 can refresh them per session."""
    p = DATA_DIR / "seed" / str(year) / "teams.csv"
    if not p.exists():
        return {}
    import csv
    return {r["source_id"]: r["color"] for r in csv.DictReader(open(p, encoding="utf-8"))}


def validate_against_official(season: Season, c: JolpicaClient) -> None:
    """Our recomputed totals must match the published standings. A mismatch
    blocks publication (the previous snapshot stays live) until reviewed or
    a correction is added to data/corrections/<year>.json."""
    from ..championship.scoring import standings

    j = c.get(f"{season.year}/driverstandings", max_age=600)
    lists = j["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return
    official = {s["Driver"]["driverId"]: float(s["points"]) for s in lists[0]["DriverStandings"]}
    ours = {s.driver_id: s.points for s in standings(season)}
    bad = {d: (ours.get(d), p) for d, p in official.items() if abs(ours.get(d, 0.0) - p) > 1e-6}
    if bad:
        raise ValueError(f"standings mismatch vs official (ours, official): {bad}")
