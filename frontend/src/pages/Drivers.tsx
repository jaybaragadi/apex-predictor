import { LineChart, ProbBar } from "../charts";
import { S, fmtPts, fullName, pct, shortName, slug, teamColor, teamOf } from "../data";
import { StatusPill } from "./Dashboard";

const sign = (v: number, d = 2) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}`;

function describeForm(v: number) {
  if (v > 0.25) return "Strongly improving";
  if (v > 0.08) return "Improving";
  if (v < -0.25) return "Strongly declining";
  if (v < -0.08) return "Declining";
  return "Steady";
}

function describeMomentum(m: number | null) {
  if (m === null) return "Not enough races";
  if (m > 0.4) return "Beating expectations";
  if (m > 0.1) return "Slightly ahead of expectations";
  if (m < -0.4) return "Below expectations";
  if (m < -0.1) return "Slightly below expectations";
  return "In line with expectations";
}

export function DriversIndex() {
  return (
    <div className="page">
      <section className="panel">
        <h2>Driver analytics</h2>
        <p className="sub">Pick a driver for title trajectory, form, reliability and teammate comparison.</p>
        <div className="driver-grid">
          {S.standings.map((s) => (
            <a key={s.driver} className="driver-card" href={`#driver-${slug(s.driver)}`}>
              <span className="team-stripe tall" style={{ background: teamColor(s.driver) }} />
              <span className="dc-pos">P{s.position}</span>
              <span className="dc-name">{fullName(s.driver)}<small>{teamOf(s.driver).name}</small></span>
              <span className="dc-pts">{fmtPts(s.points)}</span>
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}

export function DriverPage({ id }: { id: string }) {
  const d = S.drivers[id];
  const st = S.status.drivers[id];
  const standing = S.standings.find((s) => s.driver === id);
  const hist = S.history;
  const latestEx = [...hist].reverse().find((h) => h.explanations?.[id])?.explanations?.[id];
  const latestExRound = [...hist].reverse().find((h) => h.explanations?.[id])?.round;
  const next = S.forecast.event_stats?.find((e) => e.kind === "race");
  const nextD = next?.drivers[id];
  const mate = d.teammate;
  const h2h = S.forecast.head_to_head?.[id];
  const ptsSeries = [{ id, label: shortName(id), color: teamColor(id), values: d.points_series }];
  const titleSeries = [{ id, label: shortName(id), color: teamColor(id), values: hist.map((h) => h.title[id] ?? 0) }];
  const maxPts = Math.max(...S.standings.map((s) => s.points), 1);
  const ptsMax = Math.ceil(maxPts / 100) * 100;
  const ptsTicks = Array.from({ length: ptsMax / 100 + 1 }, (_, i) => i * 100);
  const leaderSeries = S.drivers[S.standings[0].driver].points_series;

  return (
    <div className="page">
      <a className="back" href="#drivers">All drivers</a>
      <section className="panel driver-head">
        <span className="team-stripe tall" style={{ background: teamColor(id) }} />
        <div className="dh-main">
          <p className="eyebrow">{teamOf(id).name}{d.number ? ` · #${d.number}` : ""}{d.nationality ? ` · ${d.nationality}` : ""}</p>
          <h1 className="dh-name">{d.name}</h1>
          {st && <StatusPill id={id} status={st.status} />}
          {st?.reason && <p className="sub">{st.reason}</p>}
        </div>
        <dl className="dh-stats">
          <div><dt>Title probability</dt><dd>{pct(S.forecast.title[id] ?? 0)}</dd></div>
          <div><dt>Championship</dt><dd>P{standing?.position ?? "—"} · {fmtPts(standing?.points ?? 0)}</dd></div>
          <div><dt>Wins · podiums</dt><dd>{standing?.wins ?? 0} · {(standing?.wins ?? 0) + (standing?.p2 ?? 0) + (standing?.p3 ?? 0)}</dd></div>
          <div><dt>P(finish season 2nd)</dt><dd>{pct(S.forecast.position_dist?.[id]?.[1])}</dd></div>
        </dl>
      </section>

      {latestEx && (
        <section className="panel explain">
          <p className="eyebrow">Why it moved · after Round {latestExRound}</p>
          <p className="explain-text">{latestEx.text}</p>
          {Math.abs(latestEx.delta) >= 0.001 && <div className="attrib">
            <span>Points effect <b>{sign(latestEx.points_effect * 100, 1)} pp</b></span>
            <span>Pace / form effect <b>{sign(latestEx.form_effect * 100, 1)} pp</b></span>
          </div>}
        </section>
      )}

      <div className="grid-2">
        <section className="panel">
          <h2>Title probability trajectory</h2>
          <LineChart series={titleSeries} xLabels={hist.map((h) => `R${h.round}`)} xTitles={hist.map((h) => `After R${h.round} · ${h.event}`)}
            height={220} directLabels={false} ariaLabel={`Title probability history for ${d.name}`} />
        </section>
        <section className="panel">
          <h2>Points vs championship leader</h2>
          <LineChart series={[...ptsSeries, ...(S.standings[0].driver !== id ? [{ id: "leader", label: "Leader", color: "var(--muted)", dashed: true, values: leaderSeries }] : [])]}
            xLabels={d.points_series.map((_, i) => `R${i + 1}`)} yMax={ptsMax} yTicks={ptsTicks} yFormat={(v) => `${Math.round(v)}`}
            height={220} ariaLabel={`Cumulative points for ${d.name}`} />
        </section>
      </div>

      <div className="grid-3">
        <section className="panel metric">
          <h3>Recent form</h3>
          <p className="metric-big">{describeForm(d.form)}</p>
          <p className="sub">Short-window minus season-baseline strength: <b>{sign(d.form)}</b> (log-strength units).</p>
        </section>
        <section className="panel metric">
          <h3>Momentum vs expectation</h3>
          <p className="metric-big">{describeMomentum(d.momentum)}</p>
          <p className="sub">Weighted average of the last five races' finish versus the model's pre-race expectation{d.momentum !== null ? <>: <b>{sign(d.momentum)}</b> σ</> : ""}.</p>
        </section>
        <section className="panel metric">
          <h3>Reliability</h3>
          <p className="metric-big">{pct(d.dnf_risk, 0)} DNF risk</p>
          <p className="sub">Per Grand Prix. Team rate {pct(teamOf(id).dnf_risk, 0)}; part of each team's risk is shared between teammates.</p>
        </section>
        <section className="panel metric">
          <h3>Teammate comparison</h3>
          <p className="metric-big">{mate ? (d.teammate_delta! >= 0 ? "Ahead of " : "Behind ") + shortName(mate) : "No current teammate"}</p>
          {mate && <p className="sub">Driver-skill gap in the same car: <b>{sign(d.teammate_delta!)}</b>. Car effects are separated out, so this is the driver's own contribution.</p>}
        </section>
        <section className="panel metric">
          <h3>Car competitiveness</h3>
          <p className="metric-big">{teamOf(id).trend > 0.05 ? "Car improving" : teamOf(id).trend < -0.05 ? "Car falling back" : "Car steady"}</p>
          <p className="sub">{teamOf(id).name} strength {teamOf(id).strength.toFixed(2)}, recent trend {sign(teamOf(id).trend)}.</p>
        </section>
        {nextD && next && (
          <section className="panel metric">
            <h3>Next: {next.name}</h3>
            <p className="metric-big">P{nextD.finish_position.toFixed(1)} expected</p>
            <p className="sub">Win {pct(nextD.win)} · podium {pct(nextD.podium)} · {nextD.exp_points.toFixed(1)} pts expected · DNF {pct(nextD.dnf, 0)}.</p>
          </section>
        )}
      </div>

      <div className="grid-2">
        <section className="panel">
          <h2>Results</h2>
          <div className="table-wrap tall">
            <table className="compact">
              <thead><tr><th>Rnd</th><th>Event</th><th className="num">Grid</th><th className="num">Sprint</th><th className="num">Race</th><th className="num">Pts</th></tr></thead>
              <tbody>
                {[...d.results].reverse().map((r) => (
                  <tr key={r.round}>
                    <td>R{r.round}</td><td>{S.calendar.find((c) => c.round === r.round)?.name.replace(" Grand Prix", " GP")}
                      {r.team !== d.team && <small className="muted"> · {S.teams[r.team]?.name}</small>}</td>
                    <td className="num">{r.grid ?? "—"}</td><td className="num">{r.sprint ?? ""}</td>
                    <td className={`num strong ${r.race && /^[RWND]$/.test(r.race) ? "dnf" : ""}`}>{r.race === "R" ? "DNF" : r.race === "W" ? "DNS" : r.race === "D" ? "DSQ" : r.race ?? "—"}</td>
                    <td className="num">{fmtPts(r.points)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <h2>Head-to-head: season finish</h2>
          <p className="sub">Probability that {shortName(id)} ends the season ahead of each rival.</p>
          {h2h ? (
            <ul className="rank-bars">
              {Object.entries(h2h).sort((a, b) => b[1] - a[1]).map(([o, p]) => (
                <li key={o}>
                  <span className="rb-name"><span className="team-stripe" style={{ background: teamColor(o) }} />vs {shortName(o)}</span>
                  <span className="rb-bar"><ProbBar p={p} color={teamColor(id)} /></span>
                  <span className="rb-val">{pct(p)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="sub">Head-to-head forecasts are computed for the top eight in the standings.</p>}
          {d.residuals.length > 0 && (
            <>
              <h3 className="mt">Expected vs actual finish (last races)</h3>
              <ul className="resid">
                {d.residuals.map((r) => (
                  <li key={r.round}>
                    <span>R{r.round}</span>
                    <span>exp P{r.expected.toFixed(1)}</span>
                    <span>got P{r.actual}</span>
                    <b className={r.z >= 0 ? "up" : "down"}>{r.z >= 0 ? "▲" : "▼"} {Math.abs(r.z).toFixed(2)}σ</b>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
