import { notFound } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import {
  MODELS, PILLARS, PillarKey, getPillarScores, getCompositeScore,
  gradeFromScore, GRADE_COLOR, FAMILY_COLOR,
} from "@/lib/data";

export function generateStaticParams() {
  return MODELS.map((m) => ({ alias: m.alias }));
}

export default async function ModelPage({ params }: { params: Promise<{ alias: string }> }) {
  const { alias } = await params;
  const model = MODELS.find((m) => m.alias === alias);
  if (!model) notFound();

  const pillarScores = getPillarScores(model);
  const composite = getCompositeScore(model);
  const grade = gradeFromScore(composite);
  const pillars = Object.keys(PILLARS) as PillarKey[];
  const modes = ["baseline", "pressure", "adversarial"] as const;
  const familyColor = FAMILY_COLOR[model.family];

  return (
    <div className="min-h-screen bg-background text-foreground">

      <Nav />

      <main className="max-w-6xl mx-auto px-4 py-8">

        {/* ── Model header ── */}
        <div className="flex items-start justify-between py-8 border-b border-border/40 mb-8">
          <div>
            <h1 className="text-4xl font-semibold tracking-tight mb-1" style={{ color: familyColor }}>
              {model.displayName}
            </h1>
            <p className="text-sm font-mono text-muted-foreground">{model.alias}</p>
          </div>
          <div className="text-right">
            <div className="text-4xl font-semibold font-mono text-foreground">{composite.toFixed(1)}</div>
            <div className="text-sm font-mono font-semibold mt-1" style={{ color: GRADE_COLOR[grade] }}>
              Grade {grade}
            </div>
          </div>
        </div>

        {/* ── Pillar breakdown ── */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold tracking-tight mb-4">Pillar Scores</h2>
          <div className="border border-border bg-card rounded-md p-6 space-y-4">
            {pillars.map((p) => {
              const score = pillarScores[p];
              const pg = score !== undefined ? gradeFromScore(score) : "F";
              const pgColor = GRADE_COLOR[pg];
              return (
                <div key={p}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm text-foreground">{PILLARS[p]}</span>
                    <div className="flex items-center gap-3">
                      {score !== undefined ? (
                        <>
                          <span className="text-sm font-mono font-semibold" style={{ color: pgColor }}>
                            {score.toFixed(1)}
                          </span>
                          <span className="text-xs font-mono font-semibold w-4" style={{ color: pgColor }}>
                            {pg}
                          </span>
                        </>
                      ) : (
                        <span className="text-muted-foreground text-sm">—</span>
                      )}
                    </div>
                  </div>
                  <div className="h-1.5 rounded-sm overflow-hidden bg-muted">
                    <div className="h-full transition-all duration-300"
                      style={{ width: `${score ?? 0}%`, background: pgColor }} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* ── Runs by mode ── */}
        <section>
          <h2 className="text-lg font-semibold tracking-tight mb-4">Runs by Mode</h2>
          <div className="space-y-4">
            {modes.map((mode) => {
              const modeRuns = model.runs.filter((r) => r.mode === mode);
              if (!modeRuns.length) return null;
              return (
                <div key={mode} className="border border-border bg-card rounded-md overflow-hidden">
                  <div className="px-4 py-2.5 border-b border-border/40 flex items-center gap-2">
                    <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
                      {mode}
                    </span>
                    <span className="text-xs text-muted-foreground opacity-50">
                      {modeRuns.length} run{modeRuns.length > 1 ? "s" : ""}
                    </span>
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/40">
                        <th className="text-left px-4 py-2 text-muted-foreground font-medium text-xs">Pillar</th>
                        <th className="text-right px-4 py-2 text-muted-foreground font-medium text-xs">Score</th>
                        <th className="text-center px-4 py-2 text-muted-foreground font-medium text-xs">Grade</th>
                        <th className="text-right px-4 py-2 text-muted-foreground font-medium text-xs">Latency</th>
                        <th className="text-right px-4 py-2 text-muted-foreground font-medium text-xs">Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {modeRuns.map((run) => {
                        const rg = gradeFromScore(run.score);
                        const rgColor = GRADE_COLOR[rg];
                        return (
                          <tr key={run.run_id} className="border-b border-border/40 last:border-0 hover:bg-muted/30 transition-colors">
                            <td className="px-4 py-2.5 text-foreground text-sm">{PILLARS[run.pillar]}</td>
                            <td className="px-4 py-2.5 text-right font-mono font-semibold text-sm"
                              style={{ color: rgColor }}>
                              {run.score.toFixed(1)}
                            </td>
                            <td className="px-4 py-2.5 text-center font-mono text-xs font-semibold"
                              style={{ color: rgColor }}>
                              {rg}
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">
                              {(run.avg_latency_ms / 1000).toFixed(1)}s
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">
                              {run.avg_tokens.toFixed(0)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        </section>

      </main>

      <footer className="border-t border-border px-4 py-6 max-w-6xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} GovBench</span>
        <span className="font-mono tracking-wider uppercase opacity-40">GOVBENCH-CANARY · DO NOT TRAIN</span>
      </footer>
    </div>
  );
}
