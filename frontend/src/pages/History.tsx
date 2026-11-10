import { useState } from "react";
import { Legend, LineChart, ProbBar, type Series } from "../charts";
import { S, fmtPts, fullName, isSecondTeammate, pct, shortName, teamColor } from "../data";
import { StatusPill } from "./Dashboard";

export function History() {
  const hist = S.history;
  const [idx, setIdx] = useState(Math.max(0, hist.findIndex((h) => h.clinched) - 1));
  const [focus, setFocus] = useState<string | null>(null);
  const row = hist[idx];
  const contenders = Object.keys(S.drivers).filter((d) => hist.some((h) => (h.title[d] ?? 0) >= 0.03))
    .sort((a, b) => Math.max(...hist.map((h) => h.title[b] ?? 0)) - Math.max(...hist.map((h) => h.title[a] ?? 0)));
  const series: Series[] = contenders.map((d) => ({ id: d, label: shortName(d), color: teamColor(d), dashed: isSecondTeammate(d), values: hist.map((h) => h.title[d] ?? 0) }));
  const clinchIdx = hist.findIndex((h) => h.clinched);
  const table = Object.entries(row.points).sort((a, b) => b[1] - a[1]).slice(0, 10);

  return (
    <div className="page">
      <section className="panel">
        <h2>Probability history</h2>
        <p className="sub">Every round stores a snapshot. Each line is the title probability published right after that round, computed only from results known at the time.</p>
        <Legend series={series} />
        <LineChart series={series} xLabels={hist.map((h) => `R${h.round}`)} xTitles={hist.map((h) => `After R${h.round} · ${h.event}`)}
          marker={clinchIdx >= 0 ? { index: clinchIdx, label: `Clinched R${hist[clinchIdx].round}` } : null} height={340} highlight={focus}
          ariaLabel="Championship probability after every round for drivers who reached at least 3%" />
      </section>

      <section className="panel">
        <div className="panel-head wrap">
          <div>
            <p className="eyebrow">Replay</p>
            <h2>After Round {row.round} · {row.event}</h2>
          </div>
          <div className="scrubber">
            <button className="btn small" onClick={() => setIdx(Math.max(0, idx - 1))} disabled={idx === 0} aria-label="Previous round">◀</button>
            <input id="round-scrub" type="range" min={0} max={hist.length - 1} value={idx} onChange={(e) => setIdx(Number(e.target.value))} aria-label="Select round" />
            <button className="btn small" onClick={() => setIdx(Math.min(hist.length - 1, idx + 1))} disabled={idx === hist.length - 1} aria-label="Next round">▶</button>
          </div>
        </div>
        <p className="sub">{row.clinched ? `Title decided: ${fullName(row.champion!)} cannot be caught.` : `${Object.values(row.status).filter((s) => s !== "ELIMINATED").length} drivers mathematically alive · ${row.remaining_grands_prix} Grands Prix and ${row.remaining_sprints} Sprints left.`}</p>
        <div className="grid-2 flush">
          <div className="table-wrap">
            <table className="compact">
              <thead><tr><th>Driver</th><th className="num">Pts</th><th className="probcol">Title</th><th>Status</th></tr></thead>
              <tbody>
                {table.map(([d, p]) => (
                  <tr key={d} onPointerEnter={() => setFocus(d)} onPointerLeave={() => setFocus(null)}>
                    <td><span className="team-stripe" style={{ background: teamColor(d) }} /> {fullName(d)}</td>
                    <td className="num">{fmtPts(p)}</td>
                    <td className="probcol"><div className="probcell"><ProbBar p={row.title[d] ?? 0} color={teamColor(d)} /><span>{pct(row.title[d] ?? 0)}</span></div></td>
                    <td><StatusPill status={row.status[d]} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="explain-list">
            <h3>What changed</h3>
            {row.explanations ? Object.entries(row.explanations)
              .filter(([d]) => Math.max(row.title[d] ?? 0, hist[idx - 1]?.title[d] ?? 0) >= 0.01)
              .sort((a, b) => Math.abs(b[1].delta) - Math.abs(a[1].delta)).slice(0, 5).map(([d, e]) => (
                <article key={d} className="explain-item">
                  <h4><span className="team-stripe" style={{ background: teamColor(d) }} /> {fullName(d)}</h4>
                  <p>{e.text}</p>
                </article>
              )) : <p className="sub">The first round has no earlier forecast to compare with.</p>}
          </div>
        </div>
      </section>
    </div>
  );
}
