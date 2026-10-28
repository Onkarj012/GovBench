import raw from "@/public/data/v2.json";

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
  classes: Record<string, number>;
}

/** Run settings for one model, from the manifest. */
export interface ModelManifest {
  backend: string;
  model_id: string;
  seeds: number;
  temperature: number | null;
}

/** One scenario in the run. */
export interface Scenario {
  id: string;
  role: string;
  pressure: string;
  decision_type: string;
  review_status: string;
  answer: string;
  pressure_direction: string;
}

/** One model with its overall summary and breakdowns. */
export interface ModelEntry {
  alias: string;
  name: string;
  family: string;
  backend: string;
  summary: Summary;
  by_stance: Record<string, Summary>;
  by_role: Record<string, Summary>;
  by_pressure: Record<string, Summary>;
  private_summary: Summary;
}

/** Shape of public/data/v2.json. The compiler checks the file against this on build. */
export interface V2Data {
  version: string;
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
  scenarios: Scenario[];
  flagged_scenarios: string[];
  models: ModelEntry[];
  cells: Record<string, Summary>;
}

export const data: V2Data = raw;

/** Finds a model by alias. */
export function findModel(alias: string): ModelEntry | undefined {
  return data.models.find((m) => m.alias === alias);
}

/** Summaries for one matrix position, one per stance that has a cell. */
export function cellsFor(
  alias: string,
  role: string,
  pressure: string,
  stances: string[],
): Summary[] {
  return stances.flatMap((stance) => {
    const cell: Summary | undefined =
      data.cells[`${alias}|${role}|${pressure}|${stance}`];
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

/** Roles that appear in scenarios or results, sorted. */
export function roleAxis(): string[] {
  return sortedUnique([
    ...data.scenarios.map((s) => s.role),
    ...data.models.flatMap((m) => Object.keys(m.by_role)),
  ]);
}

/** Pressures that appear in scenarios or results, sorted. */
export function pressureAxis(): string[] {
  return sortedUnique([
    ...data.scenarios.map((s) => s.pressure),
    ...data.models.flatMap((m) => Object.keys(m.by_pressure)),
  ]);
}

/** Turns a snake_case key into plain words. */
export function humanize(key: string): string {
  if (key === "ias") return "IAS";
  return key.replace(/_/g, " ");
}

/** Formats a 0 to 1 rate as a whole percent, or a dash when there is no value. */
export function pct(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
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
