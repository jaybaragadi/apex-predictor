// Browser port of apex/simulation/monte_carlo.py — same model inputs, same
// sampling scheme (Plackett–Luce via Gumbel-max, team shocks, correlated
// reliability, FIA countback), so What-If scenarios agree with the backend.
import type { SimInputs } from "./data";

export interface Condition { round: number; kind: "race" | "sprint"; positions: Record<string, number>; dnf: string[]; wet: boolean }
export interface WhatIfResult { title: Record<string, number>; expectedPoints: Record<string, number>; p2: Record<string, number>; n: number }

function mulberry32(a: number) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export async function simulateWhatIf(inp: SimInputs, conditions: Condition[], n = 20000, seed = 11,
  onProgress?: (f: number) => void, wetTemperature = 1.6): Promise<WhatIfResult> {
  const rnd = mulberry32(seed);
  const u = () => Math.max(rnd(), 1e-12);
  let spare: number | null = null;
  const normal = () => {
    if (spare !== null) { const s = spare; spare = null; return s; }
    const a = u(), b = rnd();
    const r = Math.sqrt(-2 * Math.log(a));
    spare = r * Math.sin(2 * Math.PI * b);
    return r * Math.cos(2 * Math.PI * b);
  };
  const gumbel = () => -Math.log(-Math.log(u()));

  const A = inp.all_drivers.length, F = inp.field.length;
  const aIdx = new Map(inp.all_drivers.map((d, i) => [d, i]));
  const fToA = inp.field.map((d) => aIdx.get(d)!);
  const fIdx = new Map(inp.field.map((d, i) => [d, i]));
  const teams = [...new Set(inp.field_team)].sort();
  const tOf = inp.field_team.map((t) => teams.indexOf(t));
  const T = teams.length;
  const qTeam = teams.map((_, k) => {
    const m = inp.dnf_race.filter((_, j) => tOf[j] === k);
    return m.length ? inp.shared_fraction * Math.min(...m) : 0;
  });
  const cond = new Map(conditions.map((c) => [`${c.round}-${c.kind}`, c]));

  const title = new Float64Array(A), expPts = new Float64Array(A), second = new Float64Array(A);
  const pts = new Float64Array(A), wins = new Float64Array(A), p2 = new Float64Array(A), p3 = new Float64Array(A);
  const z = new Float64Array(F), shock = new Float64Array(T), key = new Float64Array(F), dnf = new Uint8Array(F);
  const teamFail = new Uint8Array(T), fixed = new Int32Array(F), pos = new Int32Array(F);
  const idxs = Array.from({ length: F }, (_, i) => i);
  const order = Array.from({ length: A }, (_, i) => i);
  const sortKey = new Float64Array(A);

  for (let s = 0; s < n; s++) {
    for (let a = 0; a < A; a++) { pts[a] = inp.base_points[a]; wins[a] = inp.base_wins[a]; p2[a] = inp.base_p2[a]; p3[a] = inp.base_p3[a]; }
    for (let j = 0; j < F; j++) z[j] = normal() * inp.theta_sd[j];
    inp.events.forEach((ev, e) => {
      const c = cond.get(`${ev.round}-${ev.kind}`);
      const wet = c?.wet ?? ev.wet;
      const temp = wet ? wetTemperature : 1;
      const factor = (ev.kind === "sprint" ? inp.sprint_factor : 1) * (wet ? 1.4 : 1);
      for (let k = 0; k < T; k++) { shock[k] = normal() * inp.team_shock_sd; teamFail[k] = rnd() < qTeam[k] * factor ? 1 : 0; }
      fixed.fill(-1);
      if (c) for (const [d, p] of Object.entries(c.positions)) { const j = fIdx.get(d); if (j !== undefined) fixed[j] = p - 1; }
      const taken = new Set<number>();
      for (let j = 0; j < F; j++) {
        const g = gumbel();
        const q = qTeam[tOf[j]] * factor;
        const pInd = Math.min(1, Math.max(0, (inp.dnf_race[j] * factor - q) / Math.max(1 - q, 1e-9)));
        let out = rnd() < pInd || teamFail[tOf[j]] === 1;
        if (c && c.dnf.includes(inp.field[j])) out = true;
        if (fixed[j] >= 0) { out = false; taken.add(fixed[j]); }
        dnf[j] = out ? 1 : 0;
        key[j] = fixed[j] >= 0 ? -Infinity : out ? -1e6 + g : (inp.theta[e][j] + z[j] + shock[tOf[j]]) / temp + g;
      }
      const free: number[] = [];
      for (let p = 0; p < F; p++) if (!taken.has(p)) free.push(p);
      idxs.sort((x, y) => key[y] - key[x]);
      let r = 0;
      for (const j of idxs) { if (fixed[j] >= 0) pos[j] = fixed[j]; else pos[j] = free[r++]; }
      for (let j = 0; j < F; j++) {
        if (dnf[j]) continue;
        const a = fToA[j];
        pts[a] += ev.points[pos[j]] ?? 0;
        if (ev.kind === "race") { if (pos[j] === 0) wins[a]++; else if (pos[j] === 1) p2[a]++; else if (pos[j] === 2) p3[a]++; }
      }
    });
    for (let a = 0; a < A; a++) { sortKey[a] = pts[a] * 1e6 + wins[a] * 1e4 + p2[a] * 1e2 + p3[a]; expPts[a] += pts[a]; }
    order.sort((x, y) => sortKey[y] - sortKey[x]);
    title[order[0]]++;
    second[order[1]]++;
    if (s % 2000 === 1999) { onProgress?.((s + 1) / n); await new Promise((res) => setTimeout(res, 0)); }
  }
  const rec = (arr: Float64Array) => Object.fromEntries(inp.all_drivers.map((d, i) => [d, arr[i] / n]));
  return { title: rec(title), expectedPoints: rec(expPts), p2: rec(second), n };
}

/** Mathematical eligibility (points bound + countback) for a base state —
 * the same rule Engine A uses for official status. */
export function eligibility(inp: SimInputs, rules: { race_points: number[]; sprint_points: number[] }) {
  const nGp = inp.events.filter((e) => e.kind === "race").length;
  const nSp = inp.events.length - nGp;
  const maxGain = nGp * rules.race_points[0] + nSp * (rules.sprint_points[0] ?? 0);
  const field = new Set(inp.field);
  const out: Record<string, { alive: boolean; max: number; caps: Record<string, number> }> = {};
  inp.all_drivers.forEach((c, i) => {
    const gain = field.has(c) ? maxGain : 0;
    const cFinal = inp.base_points[i] + gain;
    const cWins = inp.base_wins[i] + (field.has(c) ? nGp : 0);
    let alive = true;
    const caps: Record<string, number> = {};
    inp.all_drivers.forEach((j, k) => {
      if (j === c) return;
      const margin = cFinal - inp.base_points[k];
      const cap = cWins > inp.base_wins[k] ? margin : cWins < inp.base_wins[k] ? margin - 0.5 : margin;
      if (cap < 0) alive = false;
      else if (field.has(j) && cap < maxGain) caps[j] = cap;
    });
    out[c] = { alive, max: cFinal, caps };
  });
  return out;
}
