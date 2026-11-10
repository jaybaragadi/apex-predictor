import { CalibrationChart } from "../charts";
import { S, fullName, pct, shortName } from "../data";

const f3 = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toFixed(3));

export function Methodology() {
  const bt = S.backtest;
  const cfg = S.model.config;
  const rows: [string, typeof bt.model][] = [["Apex model", bt.model], ["Baseline: standings-weighted", bt.baseline_standings], ["Baseline: every driver equal", bt.baseline_uniform]];
  const favHits = bt.per_round.filter((r) => r.favourite === r.winner).length;
  const changes = S.grid.change_log.filter((c: any) => c.type !== "new_driver" && c.type !== "new_team");

  return (
    <div className="page prose-page">
      <section className="panel prose">
        <p className="eyebrow">Methodology · model {S.meta.model_version} · ruleset {S.meta.rules_version}</p>
        <h1>How the probabilities are made</h1>
        <p>Apex Predictor answers three different questions with three separate engines, and never blends them into one arbitrary score.</p>
        <ol className="engines">
          <li><b>Who can still win? — mathematics.</b> For each driver, the best case is winning every remaining Grand Prix and Sprint while every rival scores as little as the rules allow. If even that cannot beat a rival (on points, then FIA countback: wins, second places, and so on), the driver is eliminated. Because rivals can always retire, this is exact and never eliminates a driver too early. A second check with constraint programming (OR-Tools CP-SAT) asks whether the title is still possible if every car finishes, which catches cases where several rivals would all need to finish low in the same races.</li>
          <li><b>Who is most likely to win? — a ranking model.</b> A Plackett–Luce model is fitted to every race, sprint and qualifying classification with recent rounds weighted more. Strength is split into driver skill (follows the driver), car strength (follows the team) and a circuit-type fit. A short-memory and long-memory fit are blended to capture current form. Results far below what the model expected (for example a pole-sitter finishing 15th after an incident) are treated as incidents rather than pace, and late retirements count against reliability, not speed.</li>
          <li><b>What has to happen? — simulation.</b> Each simulated season draws a complete finishing order for every remaining session, with shared team performance swings, correlated team reliability failures, uncertainty about each estimate, and the season's own points table. The champion of each simulated season is counted. Mathematics overrides statistics: a clinched champion is exactly 100% and an eliminated driver exactly 0%.</li>
        </ol>
        <p>Title probability and model reliability are different things. A 78% title probability says how often a driver wins the simulated championship; the scores below say how trustworthy the forecasts have been.</p>
      </section>

      <section className="panel">
        <h2>Backtest: forecasting the next Grand Prix</h2>
        <p className="sub">Rolling and leakage-free. After each round from R3, the model is refit on results known at that time and forecasts the following race. Lower is better on every score. {bt.model.n_races} races.</p>
        <div className="table-wrap">
          <table className="compact">
            <thead><tr><th>Forecaster</th><th className="num">Brier (win)</th><th className="num">Brier (podium)</th><th className="num">Log loss (podium)</th><th className="num">Log loss (winner)</th></tr></thead>
            <tbody>
              {rows.map(([name, s]) => (
                <tr key={name} className={name === "Apex model" ? "strong" : ""}>
                  <td>{name}</td><td className="num">{f3(s.brier_win)}</td><td className="num">{f3(s.brier_podium)}</td>
                  <td className="num">{f3(s.logloss_podium)}</td><td className="num">{f3(s.winner_logloss)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid-2 flush">
          <div>
            <h3>Podium calibration</h3>
            <CalibrationChart bins={bt.model.calibration_podium} />
          </div>
          <div>
            <h3>Favourite vs winner</h3>
            <p className="sub">The pre-race favourite won {favHits} of {bt.per_round.length} races.</p>
            <div className="table-wrap tall">
              <table className="compact">
                <thead><tr><th>Rnd</th><th>Favourite</th><th className="num">P(win)</th><th>Winner</th><th className="num">Winner's P</th></tr></thead>
                <tbody>
                  {bt.per_round.map((r) => (
                    <tr key={r.round}>
                      <td>R{r.round}</td><td>{shortName(r.favourite)}</td><td className="num">{pct(r.p_favourite)}</td>
                      <td className={r.winner === r.favourite ? "strong" : ""}>{r.winner ? shortName(r.winner) : "—"}</td><td className="num">{pct(r.p_winner)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <section className="panel prose">
        <h2>Settings in use</h2>
        <dl className="kv">
          <div><dt>Simulations</dt><dd>{S.meta.n_sims.toLocaleString()} for the live forecast, {S.meta.n_sims_history.toLocaleString()} per historical round, seed {S.meta.seed}</dd></div>
          <div><dt>Recency decay</dt><dd>λ = {String(cfg.lambda_long)} (season baseline) and {String(cfg.lambda_short)} (current form)</dd></div>
          <div><dt>Weight on current form</dt><dd>{String(cfg.beta)}</dd></div>
          <div><dt>Observation weights</dt><dd>race {String(cfg.w_race)}, sprint {String(cfg.w_sprint)}, qualifying {String(cfg.w_quali)}</dd></div>
          <div><dt>Incident threshold</dt><dd>{String(cfg.outlier_gap)} places below expectation</dd></div>
          <div><dt>Sharpness (calibration)</dt><dd>{String(cfg.sharpness)}</dd></div>
          <div><dt>Teammate correlation</dt><dd>shared per-race car shock, σ = {String(cfg.team_shock_sd)}</dd></div>
          <div><dt>Points</dt><dd>Grand Prix {S.rules.race_points.join("-")}; Sprint {S.rules.sprint_points.join("-")}; fastest-lap point {S.rules.fastest_lap_point ? "yes" : "no"}</dd></div>
        </dl>
        <p className="sub">Decay, form weight, sharpness and incident threshold are chosen by the rolling backtest. When several settings score within 0.5% of the best, the one with the most weight on current form is kept so the forecast stays responsive.</p>
      </section>

      <section className="panel prose">
        <h2>Known limitations</h2>
        <ul>
          <li>Settings are tuned and evaluated on the same season. With archived seasons loaded, tuning moves to earlier years only.</li>
          <li>No preseason forecast for 2026: the pipeline supports a prior from last season (discounted after a regulation reset), but the 2025 archive is not loaded yet.</li>
          <li>Weather, tyre degradation, strategy and grid penalties are not modelled from data yet. The wet-race option is a stated assumption.</li>
          <li>Circuit types and safety-car tendencies are coarse editorial categories.</li>
          <li>Countback inside a simulation uses wins, then seconds, then thirds. Deeper ties are vanishingly rare.</li>
        </ul>
      </section>

      <section className="panel prose">
        <h2>Data, grid changes and corrections</h2>
        <p>Results, standings and calendar come from the Jolpica F1 API (Ergast-compatible). Our recomputed standings must match the published table exactly before a snapshot is published; FIA classifications win any disagreement through an explicit corrections file.</p>
        <p><b>Points check:</b> {S.validation.points_issues.length === 0 ? "every result matches the 2026 points tables." : `${S.validation.points_issues.length} results differ and are under review.`}</p>
        <p><b>Next-round entry list:</b> {S.grid.field_notes.map((n: any) => n.note ?? n.type).join(" ")}</p>
        <h3>Grid changes detected this season</h3>
        <ul className="changes">
          {changes.length === 0 && <li>None.</li>}
          {changes.map((c: any, i: number) => (
            <li key={i}>{c.type === "team_switch" ? `${fullName(c.driver)} moved from ${S.teams[c.old]?.name ?? c.old} to ${S.teams[c.new]?.name ?? c.new} at Round ${c.round}.`
              : c.type === "number_change" ? `${fullName(c.driver)} changed number ${c.old} → ${c.new}.`
              : c.type === "team_renamed" ? `${c.old} renamed ${c.new}.` : JSON.stringify(c)}</li>
          ))}
        </ul>
        <p className="sub">Snapshot {S.meta.data_hash.slice(0, 12)} · generated {new Date(S.meta.generated_at).toLocaleString()} · source {S.meta.source} · built in {S.meta.runtime_seconds}s.
          Team colours identify teams only; no official logos or photography are used.</p>
      </section>
    </div>
  );
}
