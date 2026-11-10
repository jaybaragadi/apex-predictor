import { useEffect, useMemo, useState } from "react";
import { ProbBar } from "../charts";
import { S, fullName, pct, shortName, teamColor, type SimInputs } from "../data";
import { eligibility, simulateWhatIf, type Condition, type WhatIfResult } from "../sim";

type Draft = { p1: string; p2: string; p3: string; dnf: string[]; wet: boolean };
const emptyDraft = (): Draft => ({ p1: "", p2: "", p3: "", dnf: [], wet: false });
const keyOf = (round: number, kind: string) => `${round}-${kind}`;

export function Simulator() {
  const rounds = Object.keys(S.sim_inputs).map(Number).sort((a, b) => a - b);
  // Start from the most recent round where the title was still genuinely contested.
  const contested = [...S.history].reverse().find((h) => !h.clinched && Math.max(...Object.values(h.title)) < 0.9);
  const lastOpen = contested?.round ?? (S.status.clinch_round ? S.status.clinch_round - 1 : S.meta.last_round);
  const [base, setBase] = useState<number>(Math.max(rounds[0], lastOpen));
  const inp: SimInputs = S.sim_inputs[String(base)];
  const baseRow = S.history.find((h) => h.round === base)!;
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [baseline, setBaseline] = useState<WhatIfResult | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setDrafts({}); setResult(null); setBaseline(null); setError(null); }, [base]);

  const contenders = useMemo(() => {
    const el = eligibility(inp, S.rules);
    return inp.all_drivers.filter((d) => el[d]?.alive).sort((a, b) => (baseRow.title[b] ?? 0) - (baseRow.title[a] ?? 0));
  }, [inp, baseRow]);
  const fieldSorted = useMemo(() => [...inp.field].sort((a, b) => (baseRow.points[b] ?? 0) - (baseRow.points[a] ?? 0)), [inp, baseRow]);
  const events = inp.events.slice(0, 8);
  const leader = baseRow.leader;
  const challenger = contenders.find((d) => d !== leader) ?? contenders[0];

  const setDraft = (k: string, patch: Partial<Draft>) => setDrafts((p) => ({ ...p, [k]: { ...(p[k] ?? emptyDraft()), ...patch } }));

  function conditions(): Condition[] | string {
    const out: Condition[] = [];
    for (const ev of inp.events) {
      const dr = drafts[keyOf(ev.round, ev.kind)];
      if (!dr) continue;
      const picks = [dr.p1, dr.p2, dr.p3].filter(Boolean);
      if (new Set(picks).size !== picks.length) return `${ev.name} ${ev.kind}: one driver can't take two podium places.`;
      if (picks.some((p) => dr.dnf.includes(p))) return `${ev.name} ${ev.kind}: a driver can't both finish on the podium and retire.`;
      const positions: Record<string, number> = {};
      if (dr.p1) positions[dr.p1] = 1;
      if (dr.p2) positions[dr.p2] = 2;
      if (dr.p3) positions[dr.p3] = 3;
      if (picks.length || dr.dnf.length || dr.wet) out.push({ round: ev.round, kind: ev.kind, positions, dnf: dr.dnf, wet: dr.wet });
    }
    return out;
  }

  async function run() {
    const c = conditions();
    if (typeof c === "string") { setError(c); return; }
    setError(null);
    setProgress(0);
    const n = 20000;
    const b = baseline ?? await simulateWhatIf(inp, [], n, 7, (f) => setProgress(f * 0.5));
    setBaseline(b);
    const r = await simulateWhatIf(inp, c, n, 7, (f) => setProgress(0.5 + f * 0.5));
    setResult(r);
    setProgress(null);
  }

  function preset(kind: "leaderDnf" | "challengerTwo" | "challengerSprints" | "rain") {
    const next: Record<string, Draft> = {};
    const races = inp.events.filter((e) => e.kind === "race");
    if (kind === "leaderDnf" && races[0]) next[keyOf(races[0].round, "race")] = { ...emptyDraft(), dnf: [leader] };
    if (kind === "challengerTwo") races.slice(0, 2).forEach((e) => { next[keyOf(e.round, "race")] = { ...emptyDraft(), p1: challenger }; });
    if (kind === "challengerSprints") inp.events.filter((e) => e.kind === "sprint").forEach((e) => { next[keyOf(e.round, "sprint")] = { ...emptyDraft(), p1: challenger }; });
    if (kind === "rain" && races[0]) next[keyOf(races[0].round, "race")] = { ...emptyDraft(), wet: true };
    setDrafts(next);
    setResult(null);
  }

  const shown = result ? Object.keys(result.title).filter((d) => (result.title[d] > 0.0005 || (baseline?.title[d] ?? 0) > 0.0005))
    .sort((a, b) => result.title[b] - result.title[a]) : [];
  const sprintsLeft = inp.events.some((e) => e.kind === "sprint");

  return (
    <div className="page">
      <section className="panel hypo-banner" role="note">
        <span className="pill hypo">Hypothetical</span>
        <p>Scenarios run in your browser from the stored model of the selected round. They never change the official dashboard.</p>
      </section>

      <section className="panel">
        <div className="panel-head wrap">
          <div>
            <h2>Race &amp; scenario simulator</h2>
            <p className="sub">Choose a point in the season, set any results you want to force, and the model fills in everything else.</p>
          </div>
          <label className="field">
            <span>Start from</span>
            <select id="base-round" value={base} onChange={(e) => setBase(Number(e.target.value))}>
              {rounds.map((r) => (
                <option key={r} value={r}>After R{r} · {S.history.find((h) => h.round === r)?.event}{S.history.find((h) => h.round === r)?.clinched ? " (title decided)" : ""}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="sub">
          After R{base}: {baseRow.remaining_grands_prix} Grands Prix{baseRow.remaining_sprints ? ` and ${baseRow.remaining_sprints} Sprints` : ""} left.
          {" "}Can still win: {contenders.map((d) => shortName(d)).join(", ") || "nobody but the champion"}.
        </p>
        <div className="presets">
          <span className="presets-label">Quick scenarios</span>
          <button className="btn small" onClick={() => preset("leaderDnf")}>{shortName(leader)} retires next race</button>
          {challenger && challenger !== leader && <button className="btn small" onClick={() => preset("challengerTwo")}>{shortName(challenger)} wins the next two</button>}
          {sprintsLeft && challenger && <button className="btn small" onClick={() => preset("challengerSprints")}>{shortName(challenger)} wins every Sprint</button>}
          <button className="btn small" onClick={() => preset("rain")}>Rain at the next race</button>
          <button className="btn small ghost" onClick={() => { setDrafts({}); setResult(null); }}>Clear</button>
        </div>
      </section>

      <section className="panel">
        <h2>Set results {inp.events.length > events.length && <small className="muted">(next {events.length} sessions)</small>}</h2>
        <div className="sessions">
          {events.map((ev) => {
            const k = keyOf(ev.round, ev.kind);
            const dr = drafts[k] ?? emptyDraft();
            return (
              <fieldset key={k} className={`session ${dr.p1 || dr.dnf.length || dr.wet ? "set" : ""}`}>
                <legend>R{ev.round} · {ev.name.replace(" Grand Prix", "")} <span className="kind">{ev.kind === "sprint" ? "Sprint" : "Grand Prix"}</span></legend>
                {(["p1", "p2", "p3"] as const).map((p, i) => (
                  <label key={p} className="field row">
                    <span>P{i + 1}</span>
                    <select id={`${k}-${p}`} value={dr[p]} onChange={(e) => setDraft(k, { [p]: e.target.value })}>
                      <option value="">Model decides</option>
                      {fieldSorted.map((d) => <option key={d} value={d}>{fullName(d)}</option>)}
                    </select>
                  </label>
                ))}
                <label className="field row">
                  <span>DNF</span>
                  <select id={`${k}-dnf`} value="" onChange={(e) => e.target.value && setDraft(k, { dnf: [...new Set([...dr.dnf, e.target.value])] })}>
                    <option value="">Add a retirement…</option>
                    {fieldSorted.filter((d) => !dr.dnf.includes(d)).map((d) => <option key={d} value={d}>{fullName(d)}</option>)}
                  </select>
                </label>
                {dr.dnf.length > 0 && (
                  <div className="chips">
                    {dr.dnf.map((d) => (
                      <button key={d} className="chip" onClick={() => setDraft(k, { dnf: dr.dnf.filter((x) => x !== d) })} aria-label={`Remove ${fullName(d)} retirement`}>
                        {shortName(d)} DNF ✕
                      </button>
                    ))}
                  </div>
                )}
                <label className="check">
                  <input id={`${k}-wet`} type="checkbox" checked={dr.wet} onChange={(e) => setDraft(k, { wet: e.target.checked })} /> Wet race
                </label>
              </fieldset>
            );
          })}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="run-row">
          <button className="btn primary" onClick={run} disabled={progress !== null}>
            {progress !== null ? `Simulating… ${Math.round(progress * 100)}%` : "Run 20,000 simulations"}
          </button>
          <span className="sub">Wet races widen the spread of outcomes and raise retirement risk (an explicit assumption, not fitted to weather data).</span>
        </div>
      </section>

      {result && baseline && (
        <section className="panel" aria-live="polite">
          <h2>Hypothetical title odds</h2>
          <p className="sub">Compared with the same model and seed without your scenario. {result.n.toLocaleString()} simulated seasons each.</p>
          <div className="table-wrap">
            <table className="board">
              <thead><tr><th>Driver</th><th className="probcol">With scenario</th><th className="num">Without</th><th className="num">Change</th><th className="num">Exp. points</th></tr></thead>
              <tbody>
                {shown.map((d) => {
                  const delta = result.title[d] - (baseline.title[d] ?? 0);
                  return (
                    <tr key={d}>
                      <td><span className="team-stripe" style={{ background: teamColor(d) }} /> {fullName(d)}</td>
                      <td className="probcol"><div className="probcell"><ProbBar p={result.title[d]} ghost={baseline.title[d]} color={teamColor(d)} /><span>{pct(result.title[d])}</span></div></td>
                      <td className="num">{pct(baseline.title[d])}</td>
                      <td className={`num strong ${delta > 0.0005 ? "up" : delta < -0.0005 ? "down" : ""}`}>{delta > 0.0005 ? "▲" : delta < -0.0005 ? "▼" : "·"} {Math.abs(delta * 100).toFixed(1)} pp</td>
                      <td className="num">{result.expectedPoints[d].toFixed(0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
