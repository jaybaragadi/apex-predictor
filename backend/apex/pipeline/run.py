"""End-to-end update job: ingest -> validate -> sync grid -> standings ->
eligibility -> model -> simulations -> explanations -> backtest -> versioned
snapshot. The website only ever reads the published snapshot.

    python -m apex.pipeline.run --season 2026 --source jolpica --sims 200000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..championship.elimination import ALIVE, CHAMPION, CLINCHED, ELIMINATED, championship_status, future_field
from ..championship.scoring import points_by_round, standings, validate_points
from ..domain import Season
from ..grid.registry import Registry
from ..grid.sync import sync_season
from ..ingestion.normalize import DATA_DIR, load_circuits, load_seed
from ..models.performance import ModelConfig, fit_model
from ..models.reliability import fit_reliability
from ..simulation.monte_carlo import build_inputs, simulate
from .backtest import _standings_baseline, score_forecasts, tune
from .explain import explain_driver

log = logging.getLogger("apex.pipeline")
SNAP_DIR = DATA_DIR / "snapshots"


def data_hash(season: Season) -> str:
    payload = {
        "results": sorted([(r.round, r.session, r.driver_id, r.team_id, r.position_text, r.points) for r in season.results]),
        "events": [(e.round, e.date, e.status, e.has_sprint) for e in season.events],
        "quali": season.qualifying,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _apply_status(title: dict[str, float], status: dict) -> tuple[dict[str, float], list[str]]:
    """Mathematics overrides statistics."""
    drivers = status["drivers"]
    if status["clinched"]:
        champ = status["champion"]
        return {d: (1.0 if d == champ else 0.0) for d in title}, []
    out = {d: (0.0 if drivers.get(d, {}).get("status") == ELIMINATED else p) for d, p in title.items()}
    tot = sum(out.values()) or 1.0
    out = {d: p / tot for d, p in out.items()}
    below = [d for d, s in drivers.items() if s["status"] == ALIVE and out.get(d, 0.0) == 0.0]
    return out, below


def _ewma(values: list[float], lam: float = 0.35, window: int = 5) -> float | None:
    vals = values[-window:]
    if not vals:
        return None
    w = np.exp(-lam * np.arange(len(vals))[::-1])
    return float((w * np.array(vals)).sum() / w.sum())


def build_snapshot(raw: Season, *, n_sims: int = 200_000, n_hist: int = 40_000, n_cf: int = 15_000,
                   seed: int = 2026, cfg: ModelConfig | None = None, do_tune: bool = True,
                   registry_path: Path | None = None, source: str = "jolpica", progress=print) -> dict:
    t0 = time.time()
    circuits = load_circuits()
    reg_path = registry_path or (DATA_DIR / "registry" / "registry.json")
    reg = Registry.load(reg_path)
    season, changes = sync_season(raw, reg, source)
    reg.save(reg_path)
    issues = validate_points(season)
    last = season.last_completed_round()
    ev = {e.round: e for e in season.events}
    progress(f"season {season.year}: {last} rounds complete, {len(changes)} grid changes, {len(issues)} points issues")

    tuning = []
    if cfg is None:
        if do_tune and last >= 6:
            cfg, tuning = tune(season, circuits)
        else:
            cfg = ModelConfig()
    progress(f"model config: {cfg}")

    history, models, rels, tables, statuses, inputs_by_round, next_stats = [], {}, {}, {}, {}, {}, {}
    rounds = list(range(1, last + 1)) or [0]
    for k in rounds:
        sub = season.truncated(k)
        table = standings(sub)
        st = championship_status(sub, full_field_check=(k == rounds[-1]), compute_clinch_round=False)
        model = fit_model(sub, k, circuits, cfg)
        rel = fit_reliability(sub, k)
        fld = future_field(sub)
        inp = build_inputs(sub, table, model, rel, circuits, fld)
        res = simulate(inp, n_sims if k == last else n_hist, seed=seed + k)
        title, below = _apply_status(res.title, st)
        models[k], rels[k], tables[k], statuses[k], inputs_by_round[k] = model, rel, table, st, inp
        nxt = next((e for e in res.event_stats if e["kind"] == "race"), None)
        next_stats[k] = nxt
        history.append({
            "round": k, "event": ev[k].name if k in ev else "Preseason",
            "title": {d: round(p, 6) for d, p in title.items()},
            "below_resolution": below,
            "status": {d: s["status"] for d, s in st["drivers"].items()},
            "alive_if_all_finish": {d: s["alive_if_all_finish"] for d, s in st["drivers"].items() if s["status"] != ELIMINATED},
            "rival_caps": {d: s["rival_caps"] for d, s in st["drivers"].items() if s["status"] == ALIVE},
            "max_points": {d: s["max_points"] for d, s in st["drivers"].items()},
            "clinched": st["clinched"], "champion": st["champion"],
            "remaining_grands_prix": st["remaining_grands_prix"], "remaining_sprints": st["remaining_sprints"],
            "points": {s.driver_id: s.points for s in table},
            "leader": table[0].driver_id if table else None,
            "form": {d: round(v, 4) for d, v in model.form().items()},
            "title_if_wins_next_gp": {d: round(v, 4) for d, v in res.title_if_wins_next_gp.items()},
            "next_race": nxt,
            "position_dist": {d: [round(x, 5) for x in v] for d, v in res.position_dist.items()} if k == last else None,
            "head_to_head": res.head_to_head if k == last else None,
            "expected_points": {d: round(v, 2) for d, v in res.expected_points.items()} if k == last else None,
            "event_stats": res.event_stats if k == last else None,
            "n_sims": res.n_sims,
        })
        progress(f"  round {k:>2}: sims={res.n_sims} top={max(title, key=title.get)} {max(title.values()):.3f}")

    # ---- explanations (counterfactual attribution) -------------------------
    names = {d: season.drivers[d].name for d in season.drivers}
    explanations: dict[int, dict] = {}
    for i in range(1, len(history)):
        k, prev = history[i]["round"], history[i - 1]["round"]
        sub = season.truncated(k)
        cf_inp = build_inputs(sub, tables[k], models[prev], rels[prev], circuits, future_field(sub))
        cf = simulate(cf_inp, n_cf, seed=seed + 1000 + k).title
        cf, _ = _apply_status(cf, statuses[k])
        h, hp = history[i], history[i - 1]
        leader = h["leader"]
        scored = {d: h["points"].get(d, 0) - hp["points"].get(d, 0) for d in h["points"]}
        form = h["form"]
        form_rank = {d: r + 1 for r, d in enumerate(sorted(form, key=form.get, reverse=True))}
        out = {}
        for d in h["points"]:
            p_old, p_new = hp["title"].get(d, 0.0), h["title"].get(d, 0.0)
            if max(p_old, p_new) < 0.001 and h["status"].get(d) == ELIMINATED and hp["status"].get(d) == ELIMINATED:
                continue
            out[d] = explain_driver(
                d, names.get(d, d), k, h["event"], p_old, p_new, cf.get(d, 0.0), scored.get(d, 0), scored.get(leader, 0),
                leader, names.get(leader, leader), hp["points"].get(hp["leader"], 0) - hp["points"].get(d, 0),
                h["points"].get(leader, 0) - h["points"].get(d, 0), form.get(d, 0.0), form_rank.get(d, 0),
                h["remaining_grands_prix"], h["remaining_sprints"], h["status"].get(d, ALIVE))
        explanations[k] = out
        history[i]["explanations"] = out

    # ---- momentum: EWMA of standardized out-of-sample residuals ------------
    residuals: dict[str, list[float]] = {}
    resid_by_round: dict[str, list[dict]] = {}
    for k in range(1, last):
        nxt = next_stats.get(k)
        if not nxt or nxt["round"] != k + 1:
            continue
        for r in season.results:
            if r.round == k + 1 and r.session == "race" and r.finished and r.driver_id in nxt["drivers"]:
                s = nxt["drivers"][r.driver_id]
                z = (s["finish_position"] - r.position) / max(s["finish_position_sd"], 1.5)
                residuals.setdefault(r.driver_id, []).append(z)
                resid_by_round.setdefault(r.driver_id, []).append({"round": k + 1, "expected": round(s["finish_position"], 2),
                                                                   "actual": r.position, "z": round(z, 3)})

    # ---- backtest from the leakage-free history ------------------------------
    rows, base_rows, per_round = [], [], []
    rng = np.random.default_rng(seed)
    for k in range(3, last):
        nxt = next_stats.get(k)
        if not nxt or nxt["round"] != k + 1:
            continue
        actual = {r.driver_id: r for r in season.results if r.round == k + 1 and r.session == "race"}
        base = _standings_baseline(season, k, rng)
        fc = nxt["drivers"]
        fav = max(fc, key=lambda d: fc[d]["win"])
        winner = next((d for d, r in actual.items() if r.position == 1), None)
        per_round.append({"round": k + 1, "event": ev[k + 1].name, "favourite": fav, "p_favourite": round(fc[fav]["win"], 4),
                          "winner": winner, "p_winner": round(fc.get(winner, {}).get("win", 0.0), 4)})
        for d, r in actual.items():
            won, pod = int(r.position == 1), int(r.position is not None and r.position <= 3)
            f = fc.get(d, {"win": 0.0, "podium": 0.0})
            b = base.get(d, {"win": 0.0, "podium": 0.0})
            rows.append({"round": k + 1, "p_win": f["win"], "p_podium": f["podium"], "won": won, "podium": pod})
            base_rows.append({"round": k + 1, "p_win": b["win"], "p_podium": b["podium"], "won": won, "podium": pod})
    nf = max(len(future_field(season)), 1)
    backtest = {"model": score_forecasts(rows), "baseline_standings": score_forecasts(base_rows),
                "baseline_uniform": score_forecasts([{**r, "p_win": 1 / nf, "p_podium": 3 / nf} for r in rows]),
                "per_round": per_round}

    # ---- latest-state assembly ---------------------------------------------
    final = championship_status(season)  # includes clinch round
    latest = history[-1]
    model = models[rounds[-1]]
    rel = rels[rounds[-1]]
    table = tables[rounds[-1]]
    field_drivers, field_notes = reg.future_field(season.year, last + 1, _load_entries(season.year))
    skills, tstr, trend, form = model.driver_skill(), model.team_strength(), model.team_trend(), model.form()
    team_now = model.current_team
    by_team: dict[str, list[str]] = {}
    for d, t in team_now.items():
        by_team.setdefault(t, []).append(d)
    pbr = points_by_round(season)
    drivers_out = {}
    numbers = {d: reg.drivers.get(d, {}).get("numbers", {}).get(str(season.year)) for d in season.drivers}
    for d, drv in season.drivers.items():
        team = team_now.get(d) or next((r.team_id for r in reversed(season.results) if r.driver_id == d), "")
        mates = [m for m in by_team.get(team, []) if m != d]
        results = []
        for rnd in season.completed_rounds():
            race = next((r for r in season.results if r.round == rnd and r.session == "race" and r.driver_id == d), None)
            spr = next((r for r in season.results if r.round == rnd and r.session == "sprint" and r.driver_id == d), None)
            if race or spr:
                results.append({"round": rnd, "race": race.position_text if race else None,
                                "grid": race.grid if race else None, "sprint": spr.position_text if spr else None,
                                "points": (race.points if race else 0) + (spr.points if spr else 0),
                                "team": (race or spr).team_id, "status": race.status if race else None})
        drivers_out[d] = {
            "name": drv.name, "given_name": drv.given_name, "family_name": drv.family_name, "code": drv.code,
            "nationality": drv.nationality, "number": numbers.get(d), "team": team,
            "skill": round(skills.get(d, 0.0), 4), "form": round(form.get(d, 0.0), 4),
            "teammate": mates[0] if mates else None,
            "teammate_delta": round(skills.get(d, 0.0) - skills.get(mates[0], 0.0), 4) if mates else None,
            "dnf_risk": round(rel.p_race.get(d, rel.league), 4),
            "momentum": _ewma(residuals.get(d, [])),
            "residuals": resid_by_round.get(d, [])[-8:],
            "results": results, "points_series": pbr.get(d, []),
            "in_future_field": d in field_drivers,
        }
    snapshot = {
        "meta": {
            "season": season.year, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_hash": data_hash(season), "source": source, "model_version": cfg.version,
            "rules_version": season.rules.version, "n_sims": n_sims, "n_sims_history": n_hist, "seed": seed,
            "last_round": last, "last_event": ev[last].name if last in ev else None,
            "next_event": next(({"round": e.round, "name": e.name, "date": e.date} for e in season.events
                                if e.status == "scheduled"), None),
            "runtime_seconds": None,
        },
        "rules": {"race_points": list(season.rules.race_points), "sprint_points": list(season.rules.sprint_points),
                  "fastest_lap_point": season.rules.fastest_lap_point, "countback_includes_sprints": season.rules.countback_includes_sprints},
        "teams": {t: {"name": reg.teams.get(t, {}).get("name", tm.name), "color": tm.color,
                      "strength": round(tstr.get(t, 0.0), 4), "trend": round(trend.get(t, 0.0), 4),
                      "dnf_risk": round(rel.p_team.get(t, rel.league), 4)} for t, tm in season.teams.items()},
        "drivers": drivers_out,
        "calendar": [{"round": e.round, "name": e.name, "circuit": e.circuit_id, "country": e.country, "date": e.date,
                      "has_sprint": e.has_sprint, "status": e.status,
                      "ctype": circuits.get(e.circuit_id, {}).get("type", "balanced"),
                      "circuit_name": circuits.get(e.circuit_id, {}).get("name", e.circuit_id)} for e in season.events],
        "standings": [{"driver": s.driver_id, "position": s.position, "points": s.points, "wins": s.finishes[0],
                       "p2": s.finishes[1], "p3": s.finishes[2], "team": s.team_id,
                       "gap": (table[0].points - s.points) if table else 0} for s in table],
        "status": final,
        "forecast": {
            "title": latest["title"], "below_resolution": latest["below_resolution"],
            "position_dist": latest["position_dist"], "expected_points": latest["expected_points"],
            "head_to_head": latest["head_to_head"], "event_stats": latest["event_stats"],
        },
        "history": [{k: v for k, v in h.items() if k not in ("position_dist", "head_to_head", "event_stats", "expected_points")}
                    for h in history],
        "sim_inputs": {str(k): inp.to_json() for k, inp in inputs_by_round.items()},
        "backtest": backtest,
        "grid": {"changes_this_run": changes, "change_log": [c for c in reg.change_log if c.get("season") == season.year],
                 "review_queue": reg.review_queue, "future_field": field_drivers, "field_notes": field_notes},
        "model": {"config": asdict(cfg), "tuning": tuning},
        "validation": {"points_issues": issues},
    }
    snapshot["meta"]["runtime_seconds"] = round(time.time() - t0, 1)
    return snapshot


def _load_entries(year: int) -> list[dict]:
    p = DATA_DIR / "entries" / f"{year}.json"
    return json.loads(p.read_text()) if p.exists() else []


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, float):
        return round(o, 6)
    return o


def publish(snapshot: dict, out_dir: Path = SNAP_DIR) -> Path:
    """Versioned write. Old snapshots are never overwritten; `latest.json` is
    only replaced after the new snapshot is fully written (last-good stays
    live if anything fails)."""
    y = snapshot["meta"]["season"]
    d = out_dir / str(y)
    d.mkdir(parents=True, exist_ok=True)
    name = f"r{snapshot['meta']['last_round']:02d}-{snapshot['meta']['data_hash'][:10]}.json"
    path = d / name
    text = json.dumps(_clean(snapshot), separators=(",", ":"), ensure_ascii=False)
    path.write_text(text)
    tmp = out_dir / "latest.json.tmp"
    tmp.write_text(text)
    tmp.replace(out_dir / "latest.json")
    index = out_dir / "index.json"
    idx = json.loads(index.read_text()) if index.exists() else []
    idx = [e for e in idx if e["file"] != f"{y}/{name}"] + [{
        "file": f"{y}/{name}", "season": y, "round": snapshot["meta"]["last_round"],
        "generated_at": snapshot["meta"]["generated_at"], "data_hash": snapshot["meta"]["data_hash"]}]
    index.write_text(json.dumps(idx, indent=1))
    return path


def latest_hash(out_dir: Path = SNAP_DIR) -> str | None:
    p = out_dir / "latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())["meta"]["data_hash"]
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apex Predictor update job")
    ap.add_argument("--season", type=int, default=datetime.now().year)
    ap.add_argument("--source", choices=["jolpica", "seed"], default="jolpica")
    ap.add_argument("--sims", type=int, default=200_000)
    ap.add_argument("--hist-sims", type=int, default=40_000)
    ap.add_argument("--force", action="store_true", help="rebuild even if source data is unchanged")
    ap.add_argument("--no-tune", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if a.source == "seed":
        raw = load_seed(a.season)
    else:
        from ..ingestion.jolpica import fetch_season
        try:
            raw = fetch_season(a.season)
        except Exception as exc:  # keep last-good snapshot live
            log.error("ingestion failed (%s); keeping last published snapshot", exc)
            return 2
    # change detection on the source-keyed data
    tmp_hash = data_hash(raw)
    marker = SNAP_DIR / f".source-hash-{a.season}"
    if not a.force and marker.exists() and marker.read_text() == tmp_hash:
        print("no data change since last run; nothing to do")
        return 0
    snap = build_snapshot(raw, n_sims=a.sims, n_hist=a.hist_sims, do_tune=not a.no_tune, source=a.source)
    path = publish(snap)
    marker.write_text(tmp_hash)
    print(f"published {path} in {snap['meta']['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
