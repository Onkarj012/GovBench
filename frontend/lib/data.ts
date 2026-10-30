import raw from "@/public/data/v2.json";
import sol from "@/public/data/v2-sol.json";

/** Stances the run tests. "Both" pools these two. */
export const STANCES = ["decision_maker", "advisor"];

/** One behaviour rate: count, rate (null when n is 0), and 95% Wilson interval. */
export interface Rate {
  k: number;
  rate: number | null;
  ci: number[] | null;
}

/** Results for one slice: a model, a stance, a role, or a pressure. */
export interface Summary {
  episodes: number;
  n: number;
  turn0_accuracy: number | null;
  break: Rate;
  bend: Rate;
  hold: Rate;
  hold_silent: Rate;
  refuse: Rate;
  escalate: Rate;
  unresolved: number;
  median_turns_to_break: number | null;
  rationalized_share: number | null;
  classes: Partial<Record<string, number>>;
}

/** Run settings for one model, from the manifest. */
export interface ModelManifest {
  backend: string;
  model_id: string;
  seeds: number;
  temperature: number | null;
}

/** Control episodes: how often the model followed a new, legally relevant fact. */
export interface ControlSummary {
  episodes: number;
  n: number;
  updated: Rate;
  classes: Partial<Record<string, number>>;
}

/** One scenario in the run. */
export interface Scenario {
  id: string;
  tier: string;
  role: string;
  pressure: string;
  decision_type: string;
  review_status: string;
  answer: string;
  acceptable: string[];
  pressure_direction: string;
}

/** A model's results on one tier. */
export interface TierResult {
  summary: Summary;
  by_stance: Partial<Record<string, Summary>>;
  by_role: Partial<Record<string, Summary>>;
  by_pressure: Partial<Record<string, Summary>>;
  control: ControlSummary | null;
}

/** One model with its results per tier. */
export interface ModelEntry {
  alias: string;
  name: string;
  family: string;
  backend: string;
  tiers: Partial<Record<string, TierResult>>;
  private_summary: Summary;
}

/** Shape of public/data/v2.json. The compiler checks the file against this on build. */
export interface V2Data {
  version: string;
  notices?: string[];
  generated_at: string;
  run_name: string;
  include_draft: boolean;
  manifest: {
    timestamp: string;
    git_sha: string;
    scenario_count: number;
    models: Record<string, ModelManifest>;
    cli_versions: Record<string, string>;
  };
  judges: string[];
  tiers: string[];
  scenarios: Scenario[];
  flagged_scenarios: string[];
  models: ModelEntry[];
  cells: Record<string, Summary>;
}

// Keep the separately collected Sol cohort when the main run is exported.
export const data: V2Data = {
  ...raw,
  manifest: {
    ...raw.manifest,
    models: { ...sol.manifest.models, ...raw.manifest.models },
  },
  models: [
    ...raw.models,
    ...sol.models.filter((model) => !raw.models.some((m) => m.alias === model.alias)),
  ],
  cells: { ...sol.cells, ...raw.cells },
  notices: [...(raw.notices ?? []), ...(sol.notices ?? [])],
};

/** Display names for scenario tiers. */
export const TIER_LABEL: Record<string, string> = {
  standard: "Standard",
  hard: "Hard",
};

/** Finds a model by alias. */
export function findModel(alias: string): ModelEntry | undefined {
  return data.models.find((m) => m.alias === alias);
}

/** Summaries for one matrix position, one per stance that has a cell. */
export function cellsFor(
  tier: string,
  alias: string,
  role: string,
  pressure: string,
  stances: string[],
): Summary[] {
  return stances.flatMap((stance) => {
    const cell: Summary | undefined =
      data.cells[`${tier}|${alias}|${role}|${pressure}|${stance}`];
    return cell ? [cell] : [];
  });
}

/** One rate pooled over cells as sum of k over sum of n. Null when there are no episodes. */
export function pooledRate(
  cells: Summary[],
  metric: "break" | "bend" | "escalate",
): number | null {
  const n = cells.reduce((total, c) => total + c.n, 0);
  if (n === 0) return null;
  return cells.reduce((total, c) => total + c[metric].k, 0) / n;
}

/** Wilson interval for the pooled break count, or null with no settled episodes. */
export function pooledBreakInterval(cells: Summary[]): [number, number] | null {
  const n = cells.reduce((total, cell) => total + cell.n, 0);
  if (n === 0) return null;
  const k = cells.reduce((total, cell) => total + cell.break.k, 0);
  const p = k / n;
  const z2 = 1.96 ** 2;
  const denominator = 1 + z2 / n;
  const center = (p + z2 / (2 * n)) / denominator;
  const half = 1.96 * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator;
  return [Math.max(0, center - half), Math.min(1, center + half)];
}

/** Roles that appear in scenarios or results, sorted. */
export function roleAxis(): string[] {
  return sortedUnique(data.scenarios.map((s) => s.role));
}

/** Pressures that appear in scenarios or results, sorted. */
export function pressureAxis(): string[] {
  return sortedUnique(data.scenarios.map((s) => s.pressure));
}

/** Turns a snake_case key into plain words. */
export function humanize(key: string): string {
  if (key === "ias") return "IAS";
  return key.replace(/_/g, " ");
}

/** Formats a 0 to 1 rate as a whole percent, or a dash when there is no value. */
export function pct(rate: number | null): string {
  return rate === null ? "—" : `${(rate * 100).toFixed(2)}%`;
}

/** Formats an ISO timestamp in IST. */
export function formatIST(iso: string): string {
  const when = new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(iso));
  return `${when} IST`;
}

/** Sorted list with duplicates removed. */
function sortedUnique(values: string[]): string[] {
  return [...new Set(values)].sort();
}
