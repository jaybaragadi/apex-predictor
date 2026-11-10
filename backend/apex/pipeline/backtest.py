"""Rolling, leakage-free backtests.

For every round k the model is fitted on information available after round k
only, then asked to forecast round k+1's Grand Prix. Forecasts are scored
against what actually happened (Brier score, log loss, calibration). The same
harness selects the model's hyper-parameters (recency decay, form weight).
"""
from __future__ import annotations

import itertools
from dataclasses import replace

import numpy as np

from ..championship.elimination import future_field
from ..championship.scoring import standings
from ..domain import Season
from ..models.performance import ModelConfig, fit_model
from ..models.reliability import fit_reliability
from ..simulation.monte_carlo import build_inputs, simulate

EPS = 1e-4


def _next_race_forecast(season: Season, k: int, circuits: dict, cfg: ModelConfig, sims: int, seed: int):
    sub = season.truncated(k)
    model = fit_model(sub, k, circuits, cfg)
    rel = fit_reliability(sub, k)
    inp = build_inputs(sub, standings(sub), model, rel, circuits, future_field(sub))
    idx = next((i for i, e in enumerate(inp.events) if e.round == k + 1 and e.kind == "race"), None)
    if idx is None:
        return None
    inp.events = [inp.events[idx]]
    inp.theta = inp.theta[idx:idx + 1]
    return simulate(inp, sims, seed=seed + k, chunk=sims).event_stats[0]["drivers"]


def _standings_baseline(season: Season, k: int, rng: np.random.Generator, sims: int = 5000):
    """Naive baseline: Plackett–Luce with strength proportional to points so far."""
    table = standings(season.truncated(k))
    field = future_field(season.truncated(k))
    pts = {s.driver_id: s.points for s in table}
    w = np.array([pts.get(d, 0) + 1.0 for d in field])
    logw = np.log(w)
    g = rng.gumbel(size=(sims, len(field))) + logw
    order = np.argsort(-g, axis=1)
    win = np.bincount(order[:, 0], minlength=len(field)) / sims
    pod = np.bincount(order[:, :3].ravel(), minlength=len(field)) / sims
    return {d: {"win": win[i], "podium": pod[i]} for i, d in enumerate(field)}


def score_forecasts(rows: list[dict]) -> dict:
    """rows: one per (round, driver) with p_win, p_podium, won, podium."""
    if not rows:
        return {}
    pw = np.clip(np.array([r["p_win"] for r in rows]), EPS, 1 - EPS)
    pp = np.clip(np.array([r["p_podium"] for r in rows]), EPS, 1 - EPS)
    yw = np.array([r["won"] for r in rows], dtype=float)
    yp = np.array([r["podium"] for r in rows], dtype=float)
    ll = lambda p, y: float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
    winner_ll = float(-np.mean(np.log(pw[yw == 1]))) if yw.sum() else None
    bins = np.linspace(0, 1, 6)
    calib = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (pp >= lo) & (pp < hi if hi < 1 else pp <= hi)
        if m.sum():
            calib.append({"bin": f"{int(lo*100)}–{int(hi*100)}%", "predicted": float(pp[m].mean()),
                          "observed": float(yp[m].mean()), "n": int(m.sum())})
    return {
        "brier_win": float(((pw - yw) ** 2).mean()), "brier_podium": float(((pp - yp) ** 2).mean()),
        "logloss_podium": ll(pp, yp), "winner_logloss": winner_ll, "calibration_podium": calib,
        "n_races": len({r["round"] for r in rows}),
    }


def run_backtest(season: Season, circuits: dict, cfg: ModelConfig, sims: int = 20000, seed: int = 7,
                 start: int = 3) -> dict:
    rows, base_rows, per_round = [], [], []
    rng = np.random.default_rng(seed)
    last = season.last_completed_round()
    for k in range(start, last):
        fc = _next_race_forecast(season, k, circuits, cfg, sims, seed)
        if fc is None:
            continue
        actual = {r.driver_id: r for r in season.results if r.round == k + 1 and r.session == "race"}
        base = _standings_baseline(season, k, rng)
        fav = max(fc, key=lambda d: fc[d]["win"])
        winner = next((d for d, r in actual.items() if r.position == 1), None)
        per_round.append({"round": k + 1, "favourite": fav, "p_favourite": fc[fav]["win"], "winner": winner,
                          "p_winner": fc.get(winner, {}).get("win", 0.0)})
        for d, r in actual.items():
            won, pod = int(r.position == 1), int(r.position is not None and r.position <= 3)
            f = fc.get(d, {"win": 0.0, "podium": 0.0})
            rows.append({"round": k + 1, "p_win": f["win"], "p_podium": f["podium"], "won": won, "podium": pod})
            b = base.get(d, {"win": 0.0, "podium": 0.0})
            base_rows.append({"round": k + 1, "p_win": b["win"], "p_podium": b["podium"], "won": won, "podium": pod})
    n_field = 22
    uni = [{**r, "p_win": 1 / n_field, "p_podium": 3 / n_field} for r in rows]
    return {"model": score_forecasts(rows), "baseline_standings": score_forecasts(base_rows),
            "baseline_uniform": score_forecasts(uni), "per_round": per_round}


def tune(season: Season, circuits: dict, base: ModelConfig | None = None, sims: int = 6000,
         tolerance: float = 0.005) -> tuple[ModelConfig, list[dict]]:
    """Grid-search recency decay, form weight and sharpness by rolling podium
    log loss. Among configurations within `tolerance` (relative) of the best,
    the one with the largest form weight is preferred so the forecast stays
    responsive to momentum when the data cannot tell the options apart.
    Note: tuned on the same season it is evaluated on (disclosed on the
    methodology page); with more seasons, tune on earlier seasons only."""
    base = base or ModelConfig()
    grid = []
    for ll, beta, sh, gap in itertools.product([0.02, 0.06], [0.0, 0.35, 0.7], [1.2, 1.4], [6, 8, 10]):
        cfg = replace(base, lambda_long=ll, beta=beta, sharpness=sh, outlier_gap=gap)
        res = run_backtest(season, circuits, cfg, sims=sims)["model"]
        grid.append({"lambda_long": ll, "lambda_short": base.lambda_short, "beta": beta, "sharpness": sh, "outlier_gap": gap,
                     "logloss_podium": res["logloss_podium"], "brier_podium": res["brier_podium"]})
    best_ll = min(g["logloss_podium"] for g in grid)
    near = [g for g in grid if g["logloss_podium"] <= best_ll * (1 + tolerance)]
    best = max(near, key=lambda g: (g["beta"], -g["logloss_podium"]))
    cfg = replace(base, lambda_long=best["lambda_long"], beta=best["beta"], sharpness=best["sharpness"],
                  outlier_gap=best["outlier_gap"])
    return cfg, grid
