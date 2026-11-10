// Typed access to the published prediction snapshot.
import raw from "@snapshot";

export type Status = "ALIVE" | "ELIMINATED" | "CLINCHED" | "CHAMPION";

export interface SimEvent { round: number; kind: "race" | "sprint"; name: string; ctype: string; points: number[]; wet: boolean }
export interface SimInputs {
  all_drivers: string[]; base_points: number[]; base_wins: number[]; base_p2: number[]; base_p3: number[];
  field: string[]; field_team: string[]; theta: number[][]; theta_sd: number[]; team_shock_sd: number;
  dnf_race: number[]; shared_fraction: number; sprint_factor: number; events: SimEvent[];
}
export interface DriverInfo {
  name: string; given_name: string; family_name: string; code: string; nationality: string; number: number | null;
  team: string; skill: number; form: number; teammate: string | null; teammate_delta: number | null; dnf_risk: number;
  momentum: number | null; residuals: { round: number; expected: number; actual: number; z: number }[];
  results: { round: number; race: string | null; grid: number | null; sprint: string | null; points: number; team: string; status: string | null }[];
  points_series: number[]; in_future_field: boolean;
}
export interface EventDriverStat { win: number; podium: number; exp_points: number; exp_position: number; dnf: number; finish_position: number; finish_position_sd: number }
export interface EventStats { round: number; kind: string; name: string; drivers: Record<string, EventDriverStat> }
export interface Explanation { text: string; delta: number; points_effect: number; form_effect: number }
export interface HistoryRow {
  round: number; event: string; title: Record<string, number>; below_resolution: string[];
  status: Record<string, Status>; rival_caps: Record<string, Record<string, number>>; max_points: Record<string, number>;
  clinched: boolean; champion: string | null; remaining_grands_prix: number; remaining_sprints: number;
  points: Record<string, number>; leader: string; form: Record<string, number>;
  title_if_wins_next_gp: Record<string, number>; next_race: EventStats | null; n_sims: number;
  explanations?: Record<string, Explanation>;
}
export interface DriverStatus {
  driver_id: string; status: Status; points: number; max_points: number; in_future_field: boolean;
  alive_if_all_finish: boolean | null; tie_break_uncertain: boolean; rival_caps: Record<string, number>; reason: string;
}
export interface CalibrationBin { bin: string; predicted: number; observed: number; n: number }
export interface Scores { brier_win: number; brier_podium: number; logloss_podium: number; winner_logloss: number | null; calibration_podium: CalibrationBin[]; n_races: number }
export interface Snapshot {
  meta: { season: number; generated_at: string; data_hash: string; source: string; model_version: string; rules_version: string;
    n_sims: number; n_sims_history: number; seed: number; last_round: number; last_event: string | null;
    next_event: { round: number; name: string; date: string } | null; runtime_seconds: number };
  rules: { race_points: number[]; sprint_points: number[]; fastest_lap_point: boolean; countback_includes_sprints: boolean };
  teams: Record<string, { name: string; color: string; strength: number; trend: number; dnf_risk: number }>;
  drivers: Record<string, DriverInfo>;
  calendar: { round: number; name: string; circuit: string; circuit_name: string; country: string; date: string; has_sprint: boolean; status: string; ctype: string }[];
  standings: { driver: string; position: number; points: number; wins: number; p2: number; p3: number; team: string; gap: number }[];
  status: { remaining_grands_prix: number; remaining_sprints: number; max_points_available: number; clinched: boolean;
    champion: string | null; clinch_round: number | null; drivers: Record<string, DriverStatus> };
  forecast: { title: Record<string, number>; below_resolution: string[]; position_dist: Record<string, number[]>;
    expected_points: Record<string, number>; head_to_head: Record<string, Record<string, number>>; event_stats: EventStats[] };
  history: HistoryRow[];
  sim_inputs: Record<string, SimInputs>;
  backtest: { model: Scores; baseline_standings: Scores; baseline_uniform: Scores;
    per_round: { round: number; event: string; favourite: string; p_favourite: number; winner: string; p_winner: number }[] };
  grid: { changes_this_run: any[]; change_log: any[]; review_queue: any[]; future_field: string[]; field_notes: any[] };
  model: { config: Record<string, number | string | null>; tuning: Record<string, number>[] };
  validation: { points_issues: string[] };
}

export const S = raw as unknown as Snapshot;

export const driver = (id: string) => S.drivers[id];
export const teamOf = (id: string) => S.teams[S.drivers[id]?.team] ?? { name: "—", color: "#8a8f98", strength: 0, trend: 0, dnf_risk: 0 };
export const teamColor = (id: string) => teamOf(id).color || "#8a8f98";
export const shortName = (id: string) => S.drivers[id]?.family_name ?? id.replace(/^drv_/, "");
export const fullName = (id: string) => S.drivers[id]?.name ?? id;
export const code = (id: string) => S.drivers[id]?.code || shortName(id).slice(0, 3).toUpperCase();
export const eventName = (round: number) => S.calendar.find((c) => c.round === round)?.name ?? `Round ${round}`;
export const slug = (id: string) => id.replace(/^drv_/, "").replace(/_/g, "-");
export const fromSlug = (s: string) => Object.keys(S.drivers).find((d) => slug(d) === s);

/** Second driver of a team in standings order gets a dashed line so teammates stay distinguishable. */
export function isSecondTeammate(id: string): boolean {
  const team = S.drivers[id]?.team;
  const mates = S.standings.filter((s) => S.drivers[s.driver]?.team === team).map((s) => s.driver);
  return mates.indexOf(id) > 0;
}

export function pct(p: number | undefined, digits = 1): string {
  if (p === undefined || p === null || Number.isNaN(p)) return "—";
  if (p === 1) return "100%";
  if (p === 0) return "0%";
  if (p < 0.001) return "<0.1%";
  if (p > 0.999) return ">99.9%";
  return `${(p * 100).toFixed(digits)}%`;
}

export const fmtPts = (n: number) => (Number.isInteger(n) ? `${n}` : n.toFixed(1));

export const statusLabel: Record<Status, string> = {
  ALIVE: "Mathematically alive",
  ELIMINATED: "Eliminated",
  CLINCHED: "Champion · clinched",
  CHAMPION: "World Champion",
};

export const ctypeLabel: Record<string, string> = {
  street_fast: "Fast street circuit", street_slow: "Slow street circuit", power: "Power / low drag",
  high_downforce: "High downforce", balanced: "Balanced permanent",
};
