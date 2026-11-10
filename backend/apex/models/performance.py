"""Engine B — adaptive driver & team performance model.

A hierarchical, time-weighted Plackett–Luce ranking model:

    strength(i, event) = d_i  +  t_team(i, event)  +  c_team, circuit_type(event)

* d_i   — driver skill. Follows the driver across teams.
* t_T   — team / car competitiveness. Follows the car, not the driver, so a
          driver who switches teams is immediately re-based on the new car.
* c_T,k — circuit-type fit for the team (street, power, high-downforce, ...),
          heavily shrunk toward 0.

Observations are race, sprint and qualifying classifications, each weighted
by an exponential recency decay exp(-lambda * age). Two fits are produced:
a long-memory fit (season baseline) and a short-memory fit (current form).
The forecast strength blends them: theta = theta_long + beta * (theta_short -
theta_long). beta and the decay rates are selected by rolling backtests
(`apex.pipeline.backtest`), not by intuition.

Gaussian priors (MAP estimation) shrink rookies and new teams toward the
grid average and give every estimate an uncertainty (Laplace approximation),
which the simulator samples from.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from ..domain import Season


@dataclass
class ModelConfig:
    lambda_long: float = 0.02
    lambda_short: float = 0.25
    beta: float = 0.35  # weight on current form (short fit) vs baseline
    w_race: float = 1.0
    w_sprint: float = 0.6
    w_quali: float = 0.35
    sigma_driver: float = 1.5
    sigma_team: float = 1.2
    sigma_circuit: float = 0.3
    team_shock_sd: float = 0.30  # per-event shared car performance noise (teammate correlation)
    sharpness: float = 1.4  # calibration temperature on forecast strengths, chosen by backtest
    # Robust fitting: a result this many places below what the first-pass model
    # expected is treated as an incident (spin, collision, penalty) and removed
    # from that classification in the second pass. None disables.
    outlier_gap: int | None = 8
    version: str = "pl-hier-v2"


@dataclass
class Fit:
    driver_ids: list[str]
    team_ids: list[str]
    ctypes: list[str]
    d: np.ndarray
    t: np.ndarray
    c: np.ndarray  # (T, K)
    d_sd: np.ndarray
    t_sd: np.ndarray
    n_obs: np.ndarray  # effective (weighted) observations per driver


@dataclass
class PerformanceModel:
    cfg: ModelConfig
    long: Fit
    short: Fit
    current_team: dict[str, str]
    meta: dict = field(default_factory=dict)

    # ---- derived quantities --------------------------------------------------
    def _idx(self, fit: Fit):
        return {d: i for i, d in enumerate(fit.driver_ids)}, {t: i for i, t in enumerate(fit.team_ids)}

    def driver_skill(self, which: str = "blend") -> dict[str, float]:
        L, S = self.long, self.short
        out = {}
        for i, d in enumerate(L.driver_ids):
            out[d] = float(L.d[i] + (self.cfg.beta * (S.d[i] - L.d[i]) if which == "blend" else 0))
        return out

    def team_strength(self, which: str = "blend") -> dict[str, float]:
        L, S = self.long, self.short
        return {t: float(L.t[i] + (self.cfg.beta * (S.t[i] - L.t[i]) if which == "blend" else 0))
                for i, t in enumerate(L.team_ids)}

    def team_trend(self) -> dict[str, float]:
        return {t: float(self.short.t[i] - self.long.t[i]) for i, t in enumerate(self.long.team_ids)}

    def form(self) -> dict[str, float]:
        """Short-window minus long-window total strength: positive = improving."""
        di, ti = self._idx(self.long)
        out = {}
        for d, team in self.current_team.items():
            if d not in di:
                continue
            i, j = di[d], ti.get(team)
            ls = self.long.d[i] + (self.long.t[j] if j is not None else 0)
            ss = self.short.d[i] + (self.short.t[j] if j is not None else 0)
            out[d] = float(ss - ls)
        return out

    def strength(self, driver: str, team: str | None = None, ctype: str | None = None) -> tuple[float, float]:
        """Forecast log-strength and its standard deviation for a driver in a
        (possibly new) team at a circuit type."""
        team = team or self.current_team.get(driver)
        b = self.cfg.beta
        di, ti = self._idx(self.long)
        ki = {k: i for i, k in enumerate(self.long.ctypes)}
        mu, var = 0.0, 0.0
        if driver in di:
            i = di[driver]
            mu += (1 - b) * self.long.d[i] + b * self.short.d[i]
            var += self.long.d_sd[i] ** 2
        else:
            var += self.cfg.sigma_driver ** 2  # unknown driver: prior
        if team in ti:
            j = ti[team]
            mu += (1 - b) * self.long.t[j] + b * self.short.t[j]
            var += self.long.t_sd[j] ** 2
            if ctype in ki:
                k = ki[ctype]
                mu += (1 - b) * self.long.c[j, k] + b * self.short.c[j, k]
        else:
            var += self.cfg.sigma_team ** 2
        k = self.cfg.sharpness
        return float(mu * k), float(np.sqrt(var) * k)


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

def _observations(season: Season, upto: int, circuits: dict, cfg: ModelConfig):
    ev_by_round = {e.round: e for e in season.events}
    team_at: dict[tuple[int, str], str] = {}
    for r in season.results:
        if r.round <= upto:
            team_at[(r.round, r.driver_id)] = r.team_id
    obs = []  # (round, kind, [driver ids in finishing order])
    by = {}
    for r in season.results:
        if r.round > upto or not r.finished:
            continue
        by.setdefault((r.round, r.session), []).append(r)
    for (rnd, sess), rows in by.items():
        rows.sort(key=lambda x: x.position)
        obs.append((rnd, sess, [x.driver_id for x in rows]))
    for rnd, order in season.qualifying.items():
        if rnd <= upto:
            obs.append((rnd, "quali", [d for d in order if (rnd, d) in team_at]))
    out = []
    for rnd, kind, order in obs:
        if len(order) < 2:
            continue
        ev = ev_by_round.get(rnd)
        ctype = circuits.get(ev.circuit_id, {}).get("type", "balanced") if ev else "balanced"
        w = {"race": cfg.w_race, "sprint": cfg.w_sprint, "quali": cfg.w_quali}[kind]
        out.append((rnd, kind, order, [team_at[(rnd, d)] for d in order], ctype, w))
    return out


def _fit_once(obs, driver_ids, team_ids, ctypes, upto, lam, cfg: ModelConfig,
              prior_d: np.ndarray | None = None, prior_t: np.ndarray | None = None) -> Fit:
    N, T, K = len(driver_ids), len(team_ids), len(ctypes)
    di = {d: i for i, d in enumerate(driver_ids)}
    ti = {t: i for i, t in enumerate(team_ids)}
    ki = {k: i for i, k in enumerate(ctypes)}
    pd_ = prior_d if prior_d is not None else np.zeros(N)
    pt_ = prior_t if prior_t is not None else np.zeros(T)
    prepared = []
    for rnd, kind, order, teams, ctype, w in obs:
        a = np.array([di[d] for d in order])
        b = np.array([ti[t] for t in teams])
        prepared.append((a, b, ki[ctype], w * np.exp(-lam * (upto - rnd))))

    def unpack(x):
        return x[:N], x[N:N + T], x[N + T:].reshape(T, K)

    def f(x):
        d, t, c = unpack(x)
        g_d, g_t, g_c = np.zeros(N), np.zeros(T), np.zeros((T, K))
        nll = 0.0
        for a, b, k, w in prepared:
            th = d[a] + t[b] + c[b, k]
            L = np.logaddexp.accumulate(th[::-1])[::-1]  # L_s = logsumexp(th[s:])
            n = len(th)
            nll -= w * (th[:-1].sum() - L[:-1].sum())
            cum = np.cumsum(np.exp(-L[:-1]))  # sum_{s<=k} exp(-L_s)
            cum = np.concatenate([cum, cum[-1:]])  # last element (k=n-1) uses s<=n-2
            grad_th = -(np.r_[np.ones(n - 1), 0.0] - np.exp(th) * cum) * w
            np.add.at(g_d, a, grad_th)
            np.add.at(g_t, b, grad_th)
            np.add.at(g_c, (b, np.full_like(b, k)), grad_th)
        nll += ((d - pd_) ** 2).sum() / (2 * cfg.sigma_driver ** 2)
        nll += ((t - pt_) ** 2).sum() / (2 * cfg.sigma_team ** 2)
        nll += (c ** 2).sum() / (2 * cfg.sigma_circuit ** 2)
        g_d += (d - pd_) / cfg.sigma_driver ** 2
        g_t += (t - pt_) / cfg.sigma_team ** 2
        g_c += c / cfg.sigma_circuit ** 2
        return nll, np.concatenate([g_d, g_t, g_c.ravel()])

    x0 = np.concatenate([pd_, pt_, np.zeros(T * K)])
    res = minimize(f, x0, jac=True, method="L-BFGS-B", options={"maxiter": 500})
    d, t, c = unpack(res.x)

    # Laplace approximation (diagonal Fisher information) for uncertainty.
    h_d = np.full(N, 1 / cfg.sigma_driver ** 2)
    h_t = np.full(T, 1 / cfg.sigma_team ** 2)
    n_obs = np.zeros(N)
    for a, b, k, w in prepared:
        th = d[a] + t[b] + c[b, k]
        n = len(th)
        info = np.zeros(n)
        for s in range(n - 1):
            p = np.exp(th[s:] - np.logaddexp.reduce(th[s:]))
            info[s:] += p * (1 - p)
        np.add.at(h_d, a, w * info)
        np.add.at(h_t, b, w * info)
        np.add.at(n_obs, a, w)
    return Fit(list(driver_ids), list(team_ids), list(ctypes), d, t, c,
               1 / np.sqrt(h_d), 1 / np.sqrt(h_t), n_obs)


def _drop_outliers(obs, fit: Fit, gap: int):
    di = {d: i for i, d in enumerate(fit.driver_ids)}
    ti = {t: i for i, t in enumerate(fit.team_ids)}
    ki = {k: i for i, k in enumerate(fit.ctypes)}
    out, incidents = [], []
    for rnd, kind, order, teams, ctype, w in obs:
        th = np.array([fit.d[di[d]] + fit.t[ti[t]] + fit.c[ti[t], ki[ctype]] for d, t in zip(order, teams)])
        expected_rank = np.argsort(np.argsort(-th))
        keep = [i for i in range(len(order)) if i - expected_rank[i] < gap]
        for i in range(len(order)):
            if i - expected_rank[i] >= gap:
                incidents.append({"round": rnd, "session": kind, "driver": order[i], "position": i + 1,
                                  "expected": int(expected_rank[i]) + 1})
        out.append((rnd, kind, [order[i] for i in keep], [teams[i] for i in keep], ctype, w))
    return out, incidents


def fit_model(season: Season, upto: int, circuits: dict, cfg: ModelConfig | None = None,
              prior: "PerformanceModel | None" = None, prior_weight: float = 0.5) -> PerformanceModel:
    """Fit the model using only information available after round `upto`.

    `prior` (e.g. last season's model) provides prior means; car performance
    from the prior is down-weighted further after a major regulation change.
    """
    from ..rules import MAJOR_REG_CHANGE_SEASONS

    cfg = cfg or ModelConfig()
    obs = _observations(season, upto, circuits, cfg)
    driver_ids = sorted({d for o in obs for d in o[2]} | set(season.drivers))
    team_ids = sorted({t for o in obs for t in o[3]} | set(season.teams))
    ctypes = sorted({v.get("type", "balanced") for k, v in circuits.items() if not k.startswith("_")} | {"balanced"})
    pd_ = pt_ = None
    if prior is not None:
        car_w = prior_weight * (0.3 if season.year in MAJOR_REG_CHANGE_SEASONS else 1.0)
        ps, pt = prior.driver_skill(), prior.team_strength()
        pd_ = np.array([prior_weight * ps.get(d, 0.0) for d in driver_ids])
        pt_ = np.array([car_w * pt.get(t, 0.0) for t in team_ids])
    incidents: list[dict] = []
    if cfg.outlier_gap is not None and obs:
        first = _fit_once(obs, driver_ids, team_ids, ctypes, upto, cfg.lambda_long, cfg, pd_, pt_)
        obs, incidents = _drop_outliers(obs, first, cfg.outlier_gap)
    long = _fit_once(obs, driver_ids, team_ids, ctypes, upto, cfg.lambda_long, cfg, pd_, pt_)
    short = _fit_once(obs, driver_ids, team_ids, ctypes, upto, cfg.lambda_short, cfg, pd_, pt_)
    current_team: dict[str, str] = {}
    last = upto
    while last > 0 and not current_team:
        current_team = season.entries_for_round(last)
        last -= 1
    if not current_team:  # preseason: no results yet
        current_team = {}
    return PerformanceModel(cfg, long, short, current_team, {"upto": upto, "n_obs": len(obs), "incidents": incidents})
