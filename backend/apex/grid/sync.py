"""Synchronize a source-keyed Season with the identity registry and re-key it
by permanent internal ids."""
from __future__ import annotations

from dataclasses import replace

from ..domain import Driver, Season, Team
from .registry import Registry


def sync_season(season: Season, reg: Registry, source: str = "jolpica") -> tuple[Season, list[dict]]:
    before = len(reg.change_log)
    dmap: dict[str, str] = {}
    tmap: dict[str, str] = {}
    for sid, t in season.teams.items():
        tmap[sid] = reg.resolve_team(source, sid, t.name, season.year, t.color)
    for sid, d in season.drivers.items():
        dmap[sid] = reg.resolve_driver(source, sid, d.name.strip() or sid, d.code, season.year)
    for r in sorted(season.results, key=lambda r: (r.round, r.session != "race")):
        if r.team_id not in tmap:
            tmap[r.team_id] = reg.resolve_team(source, r.team_id, r.team_id, season.year)
        did = dmap.get(r.driver_id) or reg.resolve_driver(source, r.driver_id, r.driver_id, "", season.year)
        dmap[r.driver_id] = did
        if r.session == "race":
            reg.resolve_driver(source, r.driver_id, reg.drivers[did]["name"], "", season.year, r.number)
            reg.record_participation(season.year, r.round, did, tmap[r.team_id], r.number)

    drivers = {dmap[s]: replace(d, id=dmap[s]) for s, d in season.drivers.items()}
    teams = {tmap[s]: replace(t, id=tmap[s]) for s, t in season.teams.items()}
    results = [replace(r, driver_id=dmap[r.driver_id], team_id=tmap[r.team_id]) for r in season.results]
    quali = {k: [dmap.get(d, d) for d in v] for k, v in season.qualifying.items()}
    out = Season(season.year, drivers, teams, season.events, results, quali, season.rules)
    return out, reg.change_log[before:]
