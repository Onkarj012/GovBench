export type PillarKey =
  | "p1_demographic_consistency"
  | "p2_procedural_integrity"
  | "p3_corruption_resistance"
  | "p4_jurisdictional_awareness"
  | "p5_transparency_explainability"
  | "p6_minority_protection";

export const PILLARS: Record<PillarKey, string> = {
  p1_demographic_consistency: "P1: Demographic Consistency",
  p2_procedural_integrity: "P2: Procedural Integrity",
  p3_corruption_resistance: "P3: Corruption Resistance",
  p4_jurisdictional_awareness: "P4: Jurisdictional Awareness",
  p5_transparency_explainability: "P5: Transparency & Explainability",
  p6_minority_protection: "P6: Minority Protection",
};

export const FAMILY_COLOR: Record<string, string> = {
  openai: "#10a37f",
  anthropic: "#d97757",
  google: "#4285f4",
  deepseek: "#6366f1",
  moonshotai: "#8b5cf6",
  "z-ai": "#ec4899",
  unknown: "#6b7280",
};

export const GRADE_COLOR: Record<string, string> = {
  A: "#22c55e",
  B: "#84cc16",
  C: "#eab308",
  D: "#f97316",
  F: "#ef4444",
};

export function gradeFromScore(score: number): string {
  if (score >= 90) return "A";
  if (score >= 80) return "B";
  if (score >= 70) return "C";
  if (score >= 60) return "D";
  return "F";
}

export interface RunRecord {
  run_id: string;
  pillar: PillarKey;
  mode: "baseline" | "pressure" | "adversarial";
  score: number;
  avg_latency_ms: number;
  avg_tokens: number;
  parity_gap?: number;
  judge_disagreement?: boolean;
}

export interface PillarCI {
  pillar: PillarKey;
  n: number;
  mean: number;
  ci_low: number;
  ci_high: number;
}

export interface RobustnessDelta {
  pillar: PillarKey;
  baseline: number;
  pressure: number;
  delta: number;
}

export interface ModelRecord {
  alias: string;
  displayName: string;
  family: string;
  runs: RunRecord[];
  pillarCI?: PillarCI[];
  robustness?: RobustnessDelta[];
  coverageRatio?: number;
}

export const MODELS: ModelRecord[] = [
  { alias: "gpt-4o", displayName: "GPT-4o", family: "openai", runs: [] },
  { alias: "gpt-oss-120b", displayName: "GPT-OSS 120B", family: "openai", runs: [] },
  { alias: "claude-sonnet-4.6", displayName: "Claude Sonnet 4.6", family: "anthropic", runs: [] },
  { alias: "deepseek-v3", displayName: "DeepSeek V3", family: "deepseek", runs: [] },
  { alias: "deepseek-v4-flash", displayName: "DeepSeek V4 Flash", family: "deepseek", runs: [] },
  { alias: "gemini-3.1-flash-lite", displayName: "Gemini 3.1 Flash Lite", family: "google", runs: [] },
  { alias: "kimi-k2.6", displayName: "Kimi K2.6", family: "moonshotai", runs: [] },
  { alias: "glm-4.7-flash", displayName: "GLM 4.7 Flash", family: "z-ai", runs: [] },
];

export function getPillarScores(model: ModelRecord): Partial<Record<PillarKey, number>> {
  const out: Partial<Record<PillarKey, number>> = {};
  for (const run of model.runs) {
    if (!(run.pillar in out)) {
      out[run.pillar] = run.score;
    }
  }
  return out;
}

export function getCompositeScore(model: ModelRecord): number {
  const scores = Object.values(getPillarScores(model));
  if (!scores.length) return 0;
  return scores.reduce((a, b) => a + (b ?? 0), 0) / scores.length;
}

export interface LeaderboardEntry {
  alias: string;
  displayName: string;
  family: string;
  composite: number;
  pillarScores: Partial<Record<PillarKey, number>>;
  runs: RunRecord[];
}

export function getLeaderboard(): LeaderboardEntry[] {
  return MODELS
    .map((m) => ({
      alias: m.alias,
      displayName: m.displayName,
      family: m.family,
      composite: getCompositeScore(m),
      pillarScores: getPillarScores(m),
      runs: m.runs,
    }))
    .filter((e) => e.composite > 0)
    .sort((a, b) => b.composite - a.composite);
}
