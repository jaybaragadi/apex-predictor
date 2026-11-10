"""OpenF1 client (optional enrichment: weather, team colours, session data).

Free historical tier: 3 req/s and 30 req/min — everything is cached.
Live-session data requires an OpenF1 subscription and is not used by default.
"""
from __future__ import annotations

import time

import httpx

BASE = "https://api.openf1.org/v1"


class OpenF1Client:
    def __init__(self, client: httpx.Client | None = None, per_minute: int = 25):
        self.http = client or httpx.Client(timeout=20)
        self.gap = 60.0 / per_minute
        self._last = 0.0

    def get(self, endpoint: str, **params) -> list[dict]:
        wait = self.gap - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        r = self.http.get(f"{BASE}/{endpoint}", params=params)
        r.raise_for_status()
        return r.json()

    def sessions(self, year: int) -> list[dict]:
        return self.get("sessions", year=year)

    def team_colours(self, session_key: int | str = "latest") -> dict[str, str]:
        """team_name -> '#RRGGBB' from the drivers endpoint."""
        out = {}
        for d in self.get("drivers", session_key=session_key):
            if d.get("team_name") and d.get("team_colour"):
                out[d["team_name"]] = "#" + d["team_colour"]
        return out

    def rain_flag(self, session_key: int | str) -> bool:
        """True if any rainfall was recorded during the session."""
        return any(w.get("rainfall") for w in self.get("weather", session_key=session_key))
