import { useState } from "react";
import { S, fmtPts, fullName, pct, shortName, teamColor } from "../data";

export function Pathways() {
  const rounds = S.history.map((h) => h.round);
  const contested = [...S.history].reverse().find((h) => !h.clinched && Math.max(...Object.values(h.title)) < 0.9);
  const lastOpen = contested?.round ?? (S.status.clinch_round ? S.status.clinch_round - 1 : S.meta.last_round);
  const [base, setBase] = useState(lastOpen);
  const row = S.history.find((h) => h.round === base)!;
  const R = row.remaining_grands_prix, Sp = row.remaining_sprints;
  const maxGain = R * S.rules.race_points[0] + Sp * (S.rules.sprint_points[0] ?? 0);
  const alive = Object.entries(row.status).filter(([, s]) => s !== "ELIMINATED").map(([d]) => d)
    .sort((a, b) => (row.points[b] ?? 0) - (row.points[a] ?? 0));
  const leader = row.leader;

  return (
    <div className="page">
      <section className="panel">
        <div className="panel-head wrap">
          <div>
            <h2>Championship pathways</h2>
            <p className="sub">What each driver still in contention needs. The requirements are exact mathematics; the conditional odds come from the simulations.</p>
          </div>
          <label className="field">
            <span>Situation after</span>
            <select id="path-round" value={base} onChange={(e) => setBase(Number(e.target.value))}>
              {rounds.map((r) => <option key={r} value={r}>R{r} · {S.history.find((h) => h.round === r)?.event}</option>)}
            </select>
          </label>
        </div>
        {S.status.clinched && base >= (S.status.clinch_round ?? 99) && (
          <p className="notice">The title was decided at Round {S.status.clinch_round}. Pick an earlier round to explore the paths that were still open.</p>
        )}
        <p className="sub">{R} Grands Prix ({R * S.rules.race_points[0]} pts) and {Sp} Sprints ({Sp * (S.rules.sprint_points[0] ?? 0)} pts) remained: up to {maxGain} points.</p>
      </section>

      <div className="path-grid">
        {alive.map((d) => {
          const pts = row.points[d] ?? 0;
          const deficit = (row.points[leader] ?? 0) - pts;
          const caps = row.rival_caps[d] ?? {};
          const capList = Object.entries(caps).sort((a, b) => a[1] - b[1]).slice(0, 3);
          const ifWin = row.title_if_wins_next_gp?.[d];
          const isLeader = d === leader;
          return (
            <article key={d} className="panel path-card">
              <header>
                <span className="team-stripe tall" style={{ background: teamColor(d) }} />
                <div>
                  <h3>{fullName(d)}</h3>
                  <p className="sub">{fmtPts(pts)} pts · {isLeader ? "championship leader" : `${fmtPts(deficit)} behind ${shortName(leader)}`} · title {pct(row.title[d] ?? 0)}</p>
                </div>
              </header>
              {row.clinched ? (
                <p>Champion. Nothing further required.</p>
              ) : (
                <ul className="reqs">
                  <li><b>Maximum possible:</b> {fmtPts(row.max_points[d])} points.</li>
                  {!isLeader && <li><b>Must outscore {shortName(leader)}</b> by at least {fmtPts(deficit)} points over the remaining {R + Sp} sessions
                    (about {(deficit / Math.max(R + Sp, 1)).toFixed(1)} per session), or by exactly {fmtPts(deficit)} and win on countback.</li>}
                  {capList.length > 0 ? (
                    <li><b>Even winning every remaining session</b>, needs {capList.map(([o, c]) => `${shortName(o)} to score no more than ${fmtPts(c)}`).join(", ")}.</li>
                  ) : (
                    <li><b>Controls own destiny:</b> winning every remaining session guarantees the title.</li>
                  )}
                  {ifWin !== undefined && <li><b>If {shortName(d)} wins the next Grand Prix:</b> title probability {pct(ifWin)} (now {pct(row.title[d] ?? 0)}).</li>}
                </ul>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
