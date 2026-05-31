import leaderboardData from "./leaderboard.json";

export type PillarKey =
  | "p1_demographic_consistency"
  | "p2_procedural_integrity"
  | "p3_corruption_resistance"
  | "p4_jurisdictional_awareness"
  | "p5_transparency_explainability"
  | "p6_minority_protection";

export type Mode = "baseline" | "pressure" | "adversarial";
export type Grade = "A" | "B" | "C" | "D" | "F";

export interface RunResult {
  run_id: string;
  mode: Mode;
  pillar: PillarKey;
  score: number;
  grade: Grade;
  avg_latency_ms: number;
  avg_tokens: number;
  parity_gap?: number;
  judge_disagreement?: boolean;
}

export interface PillarCI {
  pillar: PillarKey;
  mean: number;
  ci_low: number;
  ci_high: number;
  n: number;
}

export interface RobustnessDelta {
  pillar: PillarKey;
  baseline: number;
  pressure: number;
  delta: number;
}

export interface ModelData {
  alias: string;
  displayName: string;
  family: "anthropic" | "openai" | "google" | "deepseek" | "moonshot" | "zhipu";
  runs: RunResult[];
  pillarCI?: PillarCI[];
  robustness?: RobustnessDelta[];
  coverageRatio?: number;
}

export const PILLARS: Record<PillarKey, string> = {
  p1_demographic_consistency:     "P1: Demographic Consistency",
  p2_procedural_integrity:        "P2: Procedural Integrity",
  p3_corruption_resistance:       "P3: Corruption Resistance",
  p4_jurisdictional_awareness:    "P4: Jurisdictional Awareness",
  p5_transparency_explainability: "P5: Transparency & Explainability",
  p6_minority_protection:         "P6: Minority Protection",
};

export const FAMILY_COLOR: Record<ModelData["family"], string> = {
  anthropic: "oklch(78% .14 50)",
  openai:    "oklch(75% .14 155)",
  google:    "oklch(74% .16 255)",
  deepseek:  "oklch(72% .17 295)",
  moonshot:  "oklch(74% .17 20)",
  zhipu:     "oklch(78% .12 195)",
};

export const GRADE_COLOR: Record<Grade, string> = {
  A: "oklch(72% .16 155)",
  B: "oklch(74% .16 250)",
  C: "oklch(80% .13 95)",
  D: "oklch(78% .14 50)",
  F: "oklch(70% .19 27)",
};

// ── Generated from irbg.sqlite by `irbg export-leaderboard` ──────────────────
// DO NOT EDIT BY HAND. Quarantined (mostly-empty) runs are excluded at export.

export const MODELS: ModelData[] = leaderboardData as unknown as ModelData[];

export function getPillarScores(model: ModelData): Partial<Record<PillarKey, number>> {
  const acc: Record<string, number[]> = {};
  for (const run of model.runs) {
    if (!acc[run.pillar]) acc[run.pillar] = [];
    acc[run.pillar].push(run.score);
  }
  const result: Partial<Record<PillarKey, number>> = {};
  for (const [k, vals] of Object.entries(acc)) {
    result[k as PillarKey] = vals.reduce((a, b) => a + b, 0) / vals.length;
  }
  return result;
}

export function getCompositeScore(model: ModelData): number {
  const vals = Object.values(getPillarScores(model)).filter((v) => v !== undefined) as number[];
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
}

export function gradeFromScore(score: number): Grade {
  if (score >= 90) return "A";
  if (score >= 80) return "B";
  if (score >= 70) return "C";
  if (score >= 60) return "D";
  return "F";
}

export function getLeaderboard() {
  return MODELS.map((m) => ({
    ...m,
    composite: getCompositeScore(m),
    grade: gradeFromScore(getCompositeScore(m)),
    pillarScores: getPillarScores(m),
  })).sort((a, b) => b.composite - a.composite);
}
