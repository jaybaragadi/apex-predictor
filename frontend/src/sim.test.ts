import { describe, expect, it } from "vitest";
import { S } from "./data";
import { eligibility, simulateWhatIf } from "./sim";

const openRound = String((S.status.clinch_round ?? S.meta.last_round + 1) - 1);
const inp = S.sim_inputs[openRound];

describe("browser simulator", () => {
  it("produces probabilities that sum to 1 and give eliminated drivers 0", async () => {
    const r = await simulateWhatIf(inp, [], 3000, 3);
    const total = Object.values(r.title).reduce((a, b) => a + b, 0);
    expect(total).toBeCloseTo(1, 9);
    const el = eligibility(inp, S.rules);
    for (const d of inp.all_drivers) if (!el[d].alive) expect(r.title[d]).toBe(0);
  });

  it("agrees with the backend forecast for the same round", async () => {
    const r = await simulateWhatIf(inp, [], 8000, 5);
    const backend = S.history.find((h) => String(h.round) === openRound)!.title;
    const top = Object.entries(backend).sort((a, b) => b[1] - a[1])[0][0];
    expect(Math.abs(r.title[top] - backend[top])).toBeLessThan(0.04);
  });

  it("respects forced results", async () => {
    const ev = inp.events.find((e) => e.kind === "race")!;
    const leader = inp.all_drivers[inp.base_points.indexOf(Math.max(...inp.base_points))];
    const rival = inp.field.find((d) => d !== leader)!;
    const base = await simulateWhatIf(inp, [], 3000, 9);
    const r = await simulateWhatIf(inp, [{ round: ev.round, kind: "race", positions: { [rival]: 1 }, dnf: [leader], wet: false }], 3000, 9);
    expect(r.expectedPoints[rival] - base.expectedPoints[rival]).toBeGreaterThan(5);
    expect(r.title[leader]).toBeLessThanOrEqual(base.title[leader]);
  });
});
