import { Celebration } from "../Celebration";
import { LineChart, ProbBar, type Series } from "../charts";
import { S, code, ctypeLabel, eventName, fmtPts, fullName, isSecondTeammate, pct, shortName, statusLabel, teamColor, teamOf } from "../data";

export function StatusPill({ id, status }: { id?: string; status: string }) {
  const below = id && S.forecast.below_resolution.includes(id);
  const cls = status === "ELIMINATED" ? "pill out" : status === "ALIVE" ? "pill alive" : "pill gold";
  const icon = status === "ELIMINATED" ? "✕" : status === "ALIVE" ? "●" : "★";
  return <span className={cls}><span aria-hidden="true">{icon}</span> {below ? "Alive · below sim resolution" : statusLabel[status as keyof typeof statusLabel]}</span>;
}

export function DriverChip({ id, withTeam = true }: { id: string; withTeam?: boolean }) {
  return (
    <span className="driver-chip">
      <span className="team-stripe" style={{ background: teamColor(id) }} aria-hidden="true" />
      <span className="driver-chip-name"><a href={`#driver-${id.replace(/^drv_/, "").replace(/_/g, "-")}`}>{fullName(id)}</a>
        {withTeam && <small>{teamOf(id).name}</small>}</span>
    </span>
  );
}

export function Dashboard({ animations, replayKey, onReplay }: { animations: boolean; replayKey: number; onReplay: () => void }) {
  const st = S.status;
  const leader = S.standings[0];
  const champion = st.champion;
  const second = S.standings[1];
  const fc = S.forecast;
  const nextStats = fc.event_stats?.find((e) => e.kind === "race") ?? null;
  const remaining = S.calendar.filter((c) => c.status === "scheduled");
  const alive = Object.values(st.drivers).filter((d) => d.status !== "ELIMINATED");
  const favourite = Object.entries(fc.title).sort((a, b) => b[1] - a[1])[0][0];
  const heroId = champion ?? favourite;
  const heroStanding = S.standings.find((s) => s.driver === heroId)!;
  const clinchEvent = st.clinch_round ? eventName(st.clinch_round) : null;

  // Runner-up fight: probability of finishing the season 2nd / 3rd.
  const runnerUp = Object.entries(fc.position_dist ?? {}).map(([d, dist]) => ({ d, p2: dist[1] ?? 0, p3: dist[2] ?? 0 }))
    .filter((r) => r.p2 + r.p3 > 0.005).sort((a, b) => b.p2 - a.p2).slice(0, 6);

  const historyTop = Object.keys(S.drivers).filter((d) => S.history.some((h) => (h.title[d] ?? 0) >= 0.08));
  const spark: Series[] = historyTop.map((d) => ({ id: d, label: shortName(d), color: teamColor(d), dashed: isSecondTeammate(d),
    values: S.history.map((h) => h.title[d] ?? 0) }));

  return (
    <div className="page">
      <section className={`hero ${champion ? "hero-champion" : ""}`} aria-labelledby="hero-name">
        {champion && <Celebration enabled={animations} replayKey={replayKey} />}
        <div className="hero-inner">
          <div className="hero-copy">
            <p className="eyebrow">
              {champion ? <>Title clinched · Round {st.clinch_round} · {clinchEvent}</> : <>Championship favourite after Round {S.meta.last_round}</>}
            </p>
            <p className="hero-kicker">{S.meta.season} {champion ? "World Drivers' Champion" : "title favourite"}</p>
            <h1 id="hero-name" className="hero-name">
              <span className="given">{S.drivers[heroId].given_name}</span> {S.drivers[heroId].family_name}
            </h1>
            <p className="hero-team">
              <span className="team-stripe" style={{ background: teamColor(heroId) }} aria-hidden="true" />
              {teamOf(heroId).name}{S.drivers[heroId].number ? ` · #${S.drivers[heroId].number}` : ""}
            </p>
            <p className="hero-note">
              {champion
                ? "No other driver can mathematically overtake the champion. The remaining races still update points, form and race analytics; the title probability stays exactly 100%."
                : `${alive.length} drivers can still mathematically win. ${pct(fc.title[heroId])} of ${S.meta.n_sims.toLocaleString()} simulated seasons end with ${shortName(heroId)} as champion.`}
            </p>
            <div className="hero-actions">
              {champion && <button className="btn gold" onClick={onReplay} disabled={!animations}>Replay celebration</button>}
              <a className="btn ghost" href="#history">Replay the title story</a>
            </div>
          </div>
          <div className="hero-figure">
            <div className="big-prob">{champion ? "100%" : pct(fc.title[heroId])}</div>
            <div className="big-prob-label">Championship win confidence</div>
            <dl className="hero-stats">
              <div><dt>Points</dt><dd>{fmtPts(heroStanding.points)}</dd></div>
              <div><dt>Lead</dt><dd>{leader.driver === heroId ? `+${fmtPts(leader.points - second.points)}` : `−${fmtPts(heroStanding.gap)}`}</dd></div>
              <div><dt>Grands Prix left</dt><dd>{st.remaining_grands_prix}</dd></div>
              <div><dt>Wins</dt><dd>{heroStanding.wins}</dd></div>
            </dl>
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="board-h">
        <div className="panel-head">
          <div>
            <h2 id="board-h">Championship board</h2>
            <p className="sub">Points and countback are official. Title probability comes from {S.meta.n_sims.toLocaleString()} simulated seasons, and the
              mathematical status always overrides it. Max points assumes winning every remaining session ({st.max_points_available} available).</p>
          </div>
        </div>
        <div className="table-wrap">
          <table className="board">
            <thead>
              <tr><th className="num">Pos</th><th>Driver</th><th className="num">Pts</th><th className="num">Gap</th><th className="num">Wins</th>
                <th className="num">Max</th><th>Status</th><th className="probcol">Title probability</th><th className="num">P(2nd)</th><th className="num">Exp. final</th></tr>
            </thead>
            <tbody>
              {S.standings.map((s) => {
                const ds = st.drivers[s.driver];
                const p = fc.title[s.driver] ?? 0;
                return (
                  <tr key={s.driver} className={ds?.status === "ELIMINATED" ? "dim" : ""}>
                    <td className="num pos">{s.position}</td>
                    <td><DriverChip id={s.driver} /></td>
                    <td className="num strong">{fmtPts(s.points)}</td>
                    <td className="num">{s.gap === 0 ? "—" : `−${fmtPts(s.gap)}`}</td>
                    <td className="num">{s.wins}</td>
                    <td className="num">{fmtPts(ds?.max_points ?? s.points)}</td>
                    <td>{ds && <StatusPill id={s.driver} status={ds.status} />}</td>
                    <td className="probcol"><div className="probcell"><ProbBar p={p} color={teamColor(s.driver)} /><span>{pct(p)}</span></div></td>
                    <td className="num">{pct(fc.position_dist?.[s.driver]?.[1])}</td>
                    <td className="num">{fc.expected_points?.[s.driver] !== undefined ? fc.expected_points[s.driver].toFixed(0) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid-2">
        {runnerUp.length > 0 && (
          <section className="panel" aria-labelledby="ru-h">
            <h2 id="ru-h">{champion ? "The fight for runner-up" : "Who finishes second?"}</h2>
            <p className="sub">Probability of ending the season 2nd and 3rd in the standings, from the same simulations.</p>
            <ul className="rank-bars">
              {runnerUp.map((r) => (
                <li key={r.d}>
                  <span className="rb-name"><span className="team-stripe" style={{ background: teamColor(r.d) }} />{shortName(r.d)}</span>
                  <span className="rb-bar"><ProbBar p={r.p2} color={teamColor(r.d)} /></span>
                  <span className="rb-val">{pct(r.p2)}</span>
                  <span className="rb-alt">P3 {pct(r.p3, 0)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {nextStats && (
          <section className="panel" aria-labelledby="next-h">
            <h2 id="next-h">Next race · {nextStats.name}</h2>
            <p className="sub">Round {nextStats.round} · {ctypeLabel[S.calendar.find((c) => c.round === nextStats.round)?.ctype ?? "balanced"]}. Forecast per driver.</p>
            <div className="table-wrap">
              <table className="compact">
                <thead><tr><th>Driver</th><th className="num">Win</th><th className="num">Podium</th><th className="num">Exp. pts</th><th className="num">DNF risk</th></tr></thead>
                <tbody>
                  {Object.entries(nextStats.drivers).sort((a, b) => b[1].win - a[1].win).slice(0, 8).map(([d, v]) => (
                    <tr key={d}>
                      <td><span className="team-stripe" style={{ background: teamColor(d) }} /> {fullName(d)}</td>
                      <td className="num strong">{pct(v.win)}</td><td className="num">{pct(v.podium)}</td>
                      <td className="num">{v.exp_points.toFixed(1)}</td><td className="num">{pct(v.dnf, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>

      <div className="grid-2">
        <section className="panel" aria-labelledby="traj-h">
          <h2 id="traj-h">Title probability, round by round</h2>
          <p className="sub">Forecast published after each round, using only information available at that moment.</p>
          <LineChart series={spark} xLabels={S.history.map((h) => `R${h.round}`)} xTitles={S.history.map((h) => `After R${h.round} · ${h.event}`)}
            marker={st.clinch_round ? { index: S.history.findIndex((h) => h.round === st.clinch_round), label: "Clinched" } : null}
            height={240} ariaLabel="Title probability history for leading contenders" />
          <a className="link-more" href="#history">Open the full history</a>
        </section>
        <section className="panel" aria-labelledby="cal-h">
          <h2 id="cal-h">Remaining calendar</h2>
          <ul className="calendar">
            {remaining.length === 0 && <li>Season complete.</li>}
            {remaining.map((c) => (
              <li key={c.round}>
                <span className="cal-round">R{c.round}</span>
                <span className="cal-name">{c.name}<small>{c.circuit_name} · {ctypeLabel[c.ctype] ?? c.ctype}</small></span>
                <span className="cal-date">{new Date(c.date + "T12:00:00Z").toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
                <span className="cal-tag">{c.has_sprint ? "Sprint + GP" : "GP"} · {c.has_sprint ? 33 : 25} pts max</span>
              </li>
            ))}
          </ul>
          <p className="sub">Entry list for Round {S.meta.last_round + 1}: {S.grid.field_notes[0]?.type === "confirmed_entry_list" ? "confirmed" : "assumed from the most recent race until a confirmed list is published"}.</p>
        </section>
      </div>
      <p className="foot-note">Leader {code(leader.driver)} · data through {S.meta.last_event} · snapshot {S.meta.data_hash.slice(0, 10)}</p>
    </div>
  );
}
