"""Read-only API over published snapshots + on-demand What-If simulations.

The site never runs the full forecast on page load; it reads the cached
snapshot. Scenario requests run a smaller conditional simulation from the
stored model inputs of the requested base round.

    uvicorn apex.api.main:app --reload
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..pipeline.run import SNAP_DIR
from ..simulation.monte_carlo import Condition, SimEvent, SimInputs, simulate

app = FastAPI(title="Apex Predictor API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@lru_cache(maxsize=8)
def _load(path: str, mtime: float) -> dict:
    return json.loads(Path(path).read_text())


def snapshot(file: str = "latest.json") -> dict:
    p = SNAP_DIR / file
    if not p.exists():
        raise HTTPException(404, "no snapshot published yet")
    return _load(str(p), p.stat().st_mtime)


@app.get("/api/health")
def health():
    s = snapshot()
    return {"ok": True, "season": s["meta"]["season"], "last_round": s["meta"]["last_round"],
            "generated_at": s["meta"]["generated_at"]}


@app.get("/api/snapshot")
def latest():
    return snapshot()


@app.get("/api/snapshots")
def list_snapshots():
    idx = SNAP_DIR / "index.json"
    return json.loads(idx.read_text()) if idx.exists() else []


@app.get("/api/drivers/{driver_id}")
def driver(driver_id: str):
    s = snapshot()
    if driver_id not in s["drivers"]:
        raise HTTPException(404, "unknown driver")
    return {"driver": s["drivers"][driver_id], "status": s["status"]["drivers"].get(driver_id),
            "title": s["forecast"]["title"].get(driver_id),
            "history": [{"round": h["round"], "p": h["title"].get(driver_id, 0.0)} for h in s["history"]]}


@app.get("/api/eligibility")
def eligibility():
    return snapshot()["status"]


class ConditionIn(BaseModel):
    round: int
    kind: str = "race"
    positions: dict[str, int] = Field(default_factory=dict)
    dnf: list[str] = Field(default_factory=list)
    wet: bool | None = None


class ScenarioIn(BaseModel):
    base_round: int | None = None
    conditions: list[ConditionIn] = Field(default_factory=list)
    n_sims: int = Field(30_000, ge=1_000, le=200_000)
    seed: int = 1


def inputs_from_json(j: dict) -> SimInputs:
    return SimInputs(
        j["all_drivers"], np.array(j["base_points"], float), np.array(j["base_wins"], float),
        np.array(j["base_p2"], float), np.array(j["base_p3"], float), j["field"], j["field_team"],
        np.array(j["theta"], float).reshape(len(j["events"]), len(j["field"])), np.array(j["theta_sd"], float),
        j["team_shock_sd"], np.array(j["dnf_race"], float), j["shared_fraction"], j["sprint_factor"],
        [SimEvent(**e) for e in j["events"]])


@app.post("/api/scenario")
def scenario(body: ScenarioIn):
    s = snapshot()
    base = str(body.base_round or s["meta"]["last_round"])
    if base not in s["sim_inputs"]:
        raise HTTPException(400, f"no model inputs stored for round {base}")
    inp = inputs_from_json(s["sim_inputs"][base])
    valid = {(e.round, e.kind) for e in inp.events}
    for c in body.conditions:
        if (c.round, c.kind) not in valid:
            raise HTTPException(400, f"round {c.round} {c.kind} is not a remaining session at base round {base}")
        pos = list(c.positions.values())
        if len(pos) != len(set(pos)):
            raise HTTPException(400, "two drivers cannot share a finishing position")
    res = simulate(inp, body.n_sims, seed=body.seed,
                   conditions=[Condition(c.round, c.kind, c.positions, c.dnf, c.wet) for c in body.conditions])
    return {"hypothetical": True, "base_round": int(base), "n_sims": res.n_sims, "title": res.title,
            "expected_points": res.expected_points}
