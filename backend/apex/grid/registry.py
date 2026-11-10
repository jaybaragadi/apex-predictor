"""Engine D — dynamic F1 grid & season management.

Everything that can change in F1 is data here, never code:

* Drivers get a permanent internal id (``drv_*``) the first time they appear.
  Car numbers, codes and team assignments are time-dependent attributes, so a
  number change (33 -> 3, champion taking #1) never creates a new driver.
* Teams get a permanent id (``team_*``); commercial renames become aliases and
  successor/predecessor links are explicit, so history is never split.
* Each sync compares source records against stored identities and emits a
  change log (new driver, team switch, number change, new team, rename).
  Ambiguous matches (same name, different source id) go to a review queue
  instead of being merged automatically.
* Entry status distinguishes ``announced`` / ``confirmed`` / ``participated``;
  only confirmed entries or actual participation feed the simulator. Rumours
  never do.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Registry:
    drivers: dict = field(default_factory=dict)
    teams: dict = field(default_factory=dict)
    assignments: list = field(default_factory=list)
    review_queue: list = field(default_factory=list)
    change_log: list = field(default_factory=list)
    _src_driver: dict = field(default_factory=dict, repr=False)
    _src_team: dict = field(default_factory=dict, repr=False)

    # ---- persistence ----------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "Registry":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        reg = cls(raw.get("drivers", {}), raw.get("teams", {}), raw.get("assignments", []),
                  raw.get("review_queue", []), raw.get("change_log", []))
        reg._reindex()
        return reg

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"drivers": self.drivers, "teams": self.teams, "assignments": self.assignments,
                                    "review_queue": self.review_queue, "change_log": self.change_log[-500:]},
                                   indent=1, ensure_ascii=False))

    def _reindex(self) -> None:
        self._src_driver = {(src, sid): did for did, d in self.drivers.items() for src, sid in d["source_ids"].items()}
        self._src_team = {(src, sid): tid for tid, t in self.teams.items() for src, sid in t["source_ids"].items()}

    def _log(self, kind: str, **kw) -> None:
        self.change_log.append({"type": kind, **kw})

    # ---- identity resolution --------------------------------------------------
    def resolve_driver(self, source: str, source_id: str, full_name: str, code: str = "",
                       season: int | None = None, number: int | None = None) -> str:
        did = self._src_driver.get((source, source_id))
        if did is None:
            same_name = [k for k, d in self.drivers.items() if d["name"].casefold() == full_name.casefold()]
            did = f"drv_{source_id}"
            n = 2
            while did in self.drivers:
                did = f"drv_{source_id}_{n}"; n += 1
            self.drivers[did] = {"name": full_name, "code": code, "source_ids": {source: source_id}, "numbers": {}}
            self._src_driver[(source, source_id)] = did
            if same_name:
                self.review_queue.append({"type": "possible_duplicate_driver", "new": did, "existing": same_name,
                                          "name": full_name, "note": "Not merged automatically; confirm identity."})
            self._log("new_driver", driver=did, name=full_name, season=season)
        d = self.drivers[did]
        if code and not d.get("code"):
            d["code"] = code
        if season is not None and number is not None:
            prev = d["numbers"].get(str(season))
            if prev is not None and prev != number:
                self._log("number_change", driver=did, season=season, old=prev, new=number)
            elif prev is None:
                last = [v for s, v in sorted(d["numbers"].items()) if int(s) < season]
                if last and last[-1] != number:
                    self._log("number_change", driver=did, season=season, old=last[-1], new=number)
            d["numbers"][str(season)] = number
        return did

    def resolve_team(self, source: str, source_id: str, name: str, season: int | None = None,
                     color: str | None = None) -> str:
        tid = self._src_team.get((source, source_id))
        if tid is None:
            tid = f"team_{source_id}"
            self.teams[tid] = {"name": name, "aliases": [name], "source_ids": {source: source_id},
                               "predecessor": None, "colors": {}}
            self._src_team[(source, source_id)] = tid
            self._log("new_team", team=tid, name=name, season=season)
        t = self.teams[tid]
        if name and name != t["name"]:
            self._log("team_renamed", team=tid, old=t["name"], new=name, season=season)
            t["name"] = name
            if name not in t["aliases"]:
                t["aliases"].append(name)
        if color and season is not None:
            t["colors"][str(season)] = color
        return tid

    def link_successor(self, old_team: str, new_team: str) -> None:
        """Record a sale / rebrand where history should carry forward cautiously."""
        self.teams[new_team]["predecessor"] = old_team
        self._log("team_succession", old=old_team, new=new_team)

    # ---- entries ----------------------------------------------------------------
    def record_participation(self, season: int, rnd: int, driver: str, team: str, number: int | None) -> None:
        prev = [a for a in self.assignments if a["driver"] == driver and (a["season"], a["round"]) < (season, rnd)
                and a["status"] == "participated"]
        exists = any(a["season"] == season and a["round"] == rnd and a["driver"] == driver for a in self.assignments)
        if exists:
            return
        if prev:
            last = max(prev, key=lambda a: (a["season"], a["round"]))
            if last["team"] != team:
                self._log("team_switch", driver=driver, season=season, round=rnd, old=last["team"], new=team)
        self.assignments.append({"season": season, "round": rnd, "driver": driver, "team": team,
                                 "number": number, "status": "participated"})

    def future_field(self, season: int, next_round: int, confirmed: list[dict] | None = None) -> tuple[list[str], list[dict]]:
        """Drivers expected in `next_round`. Confirmed entries win; otherwise
        each team's most recent participants are assumed (flagged)."""
        notes: list[dict] = []
        if confirmed:
            drivers = [d for e in confirmed if e.get("round") == next_round and e.get("status") == "confirmed"
                       for d in e["drivers"]]
            if drivers:
                return drivers, [{"type": "confirmed_entry_list", "round": next_round}]
        part = [a for a in self.assignments if a["season"] == season and a["round"] < next_round]
        if not part:
            return [], notes
        last_round = max(a["round"] for a in part)
        drivers = [a["driver"] for a in part if a["round"] == last_round]
        notes.append({"type": "assumed_from_last_round", "round": last_round,
                      "note": "No confirmed entry list yet; using the most recent participants per team."})
        return drivers, notes

    def regular_drivers(self, season: int) -> dict[str, list[str]]:
        """team -> drivers ordered by starts this season (for reserve detection)."""
        out: dict[str, dict[str, int]] = {}
        for a in self.assignments:
            if a["season"] == season:
                out.setdefault(a["team"], {}).setdefault(a["driver"], 0)
                out[a["team"]][a["driver"]] += 1
        return {t: sorted(d, key=d.get, reverse=True) for t, d in out.items()}
