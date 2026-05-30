import Nav from "@/components/Nav";
import { MODELS, PILLARS, PillarKey, FAMILY_COLOR, GRADE_COLOR, gradeFromScore, getLeaderboard } from "@/lib/data";

const pillars = Object.keys(PILLARS) as PillarKey[];
const leaderboard = getLeaderboard();

export default function DataPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Nav active="Data" />

      <div className="max-w-6xl mx-auto px-4 py-12 space-y-16">

        <div>
          <p className="text-xs font-mono text-muted-foreground tracking-wider uppercase mb-3">Raw data · v1.0</p>
          <h1 className="text-4xl font-semibold tracking-tight text-foreground mb-3">Data Explorer</h1>
          <p className="text-muted-foreground leading-relaxed max-w-[60ch]">
            All benchmark runs, per-pillar scores, mode comparisons, and token efficiency data.
          </p>
        </div>

        {/* ── All runs ── */}
        <section>
          <h2 className="text-xl font-semibold tracking-tight mb-1">All Runs</h2>
          <p className="text-sm text-muted-foreground mb-5">Every scored run across all models, pillars, and modes.</p>
          <div className="border border-border bg-card rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  {["Model", "Mode", "Pillar", "Score", "Grade", "Latency", "Tokens"].map((h, i) => (
                    <th key={h} className={`px-4 py-2.5 text-muted-foreground font-medium text-xs ${i >= 3 ? "text-right" : "text-left"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MODELS.flatMap((m) =>
                  m.runs.map((r) => {
                    const g = gradeFromScore(r.score);
                    return (
                      <tr key={r.run_id} className="border-b border-border/40 last:border-0 hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-2 text-sm font-medium" style={{ color: FAMILY_COLOR[m.family] }}>{m.displayName}</td>
                        <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{r.mode}</td>
                        <td className="px-4 py-2 text-xs text-muted-foreground">{PILLARS[r.pillar]}</td>
                        <td className="px-4 py-2 text-right font-mono text-sm font-semibold" style={{ color: GRADE_COLOR[g] }}>{r.score.toFixed(1)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs font-semibold" style={{ color: GRADE_COLOR[g] }}>{g}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">{(r.avg_latency_ms / 1000).toFixed(1)}s</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">{r.avg_tokens.toFixed(0)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Per-pillar explorer ── */}
        <section>
          <h2 className="text-xl font-semibold tracking-tight mb-1">Per-Pillar Rankings</h2>
          <p className="text-sm text-muted-foreground mb-5">All models ranked on each pillar (average across modes).</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {pillars.map((p) => {
              const rows = leaderboard
                .map((m) => ({ name: m.displayName, family: m.family, score: m.pillarScores[p] }))
                .filter((r) => r.score !== undefined)
                .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
              return (
                <div key={p} className="border border-border bg-card rounded-md overflow-hidden">
                  <div className="px-4 py-3 border-b border-border/40">
                    <div className="text-xs font-mono text-muted-foreground tracking-wider uppercase">{p.split("_")[0]}</div>
                    <div className="text-sm font-semibold text-foreground mt-0.5">{PILLARS[p].replace(/^P\d+: /, "")}</div>
                  </div>
                  <div className="p-3 space-y-2">
                    {rows.length === 0 && (
                      <p className="text-xs text-muted-foreground px-1">No data</p>
                    )}
                    {rows.map((r, i) => {
                      const g = gradeFromScore(r.score ?? 0);
                      return (
                        <div key={r.name} className="flex items-center gap-2">
                          <span className="text-xs font-mono text-muted-foreground w-3 shrink-0">{i + 1}</span>
                          <span className="text-xs flex-1 truncate" style={{ color: FAMILY_COLOR[r.family] }}>{r.name}</span>
                          <span className="text-xs font-mono font-semibold shrink-0" style={{ color: GRADE_COLOR[g] }}>
                            {r.score?.toFixed(1)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* ── Mode comparison ── */}
        <section>
          <h2 className="text-xl font-semibold tracking-tight mb-1">Baseline vs. Pressure</h2>
          <p className="text-sm text-muted-foreground mb-5">
            Score delta when moving from baseline to pressure mode. Negative = degradation under time pressure.
          </p>
          <div className="border border-border bg-card rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium text-xs">Model</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium text-xs">Pillar</th>
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Baseline</th>
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Pressure</th>
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Δ</th>
                </tr>
              </thead>
              <tbody>
                {MODELS.flatMap((m) => {
                  const pairs: { pillar: PillarKey; baseline: number; pressure: number }[] = [];
                  for (const p of pillars) {
                    const b = m.runs.find((r) => r.mode === "baseline" && r.pillar === p);
                    const pr = m.runs.find((r) => r.mode === "pressure" && r.pillar === p);
                    if (b && pr) pairs.push({ pillar: p, baseline: b.score, pressure: pr.score });
                  }
                  return pairs.map(({ pillar, baseline, pressure }) => {
                    const delta = pressure - baseline;
                    return (
                      <tr key={`${m.alias}-${pillar}`} className="border-b border-border/40 last:border-0 hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-2 text-sm font-medium" style={{ color: FAMILY_COLOR[m.family] }}>{m.displayName}</td>
                        <td className="px-4 py-2 text-xs text-muted-foreground">{PILLARS[pillar]}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs" style={{ color: GRADE_COLOR[gradeFromScore(baseline)] }}>{baseline.toFixed(1)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs" style={{ color: GRADE_COLOR[gradeFromScore(pressure)] }}>{pressure.toFixed(1)}</td>
                        <td className={`px-4 py-2 text-right font-mono text-xs font-semibold ${delta >= 0 ? "" : ""}`}
                          style={{ color: delta >= 0 ? GRADE_COLOR["A"] : GRADE_COLOR["F"] }}>
                          {delta >= 0 ? "+" : ""}{delta.toFixed(1)}
                        </td>
                      </tr>
                    );
                  });
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Token efficiency ── */}
        <section>
          <h2 className="text-xl font-semibold tracking-tight mb-1">Token Efficiency</h2>
          <p className="text-sm text-muted-foreground mb-5">
            Average tokens and latency per model. Higher score at lower token count = more efficient.
          </p>
          <div className="border border-border bg-card rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium text-xs">Model</th>
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Avg tokens</th>
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Avg latency</th>
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Composite</th>
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Score / 100 tok</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard
                  .map((m) => {
                    const avgTok = m.runs.reduce((s, r) => s + r.avg_tokens, 0) / m.runs.length;
                    const avgLat = m.runs.reduce((s, r) => s + r.avg_latency_ms, 0) / m.runs.length;
                    const efficiency = avgTok > 0 ? (m.composite / avgTok) * 100 : 0;
                    return { ...m, avgTok, avgLat, efficiency };
                  })
                  .sort((a, b) => b.efficiency - a.efficiency)
                  .map((m) => (
                    <tr key={m.alias} className="border-b border-border/40 last:border-0 hover:bg-muted/20 transition-colors">
                      <td className="px-4 py-2.5 text-sm font-medium" style={{ color: FAMILY_COLOR[m.family] }}>{m.displayName}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">{m.avgTok.toFixed(0)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">{(m.avgLat / 1000).toFixed(1)}s</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs" style={{ color: GRADE_COLOR[gradeFromScore(m.composite)] }}>{m.composite.toFixed(1)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">{m.efficiency.toFixed(2)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            Score / 100 tokens = composite score ÷ avg tokens × 100. Higher is better.
          </p>
        </section>

        {/* ── Run coverage ── */}
        <section>
          <h2 className="text-xl font-semibold tracking-tight mb-1">Run Coverage</h2>
          <p className="text-sm text-muted-foreground mb-5">Which pillars and modes have been run for each model.</p>
          <div className="border border-border bg-card rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium text-xs">Model</th>
                  {pillars.map((p) => (
                    <th key={p} className="text-center px-3 py-2.5 text-muted-foreground font-medium text-xs">
                      {p.split("_")[0].toUpperCase()}
                    </th>
                  ))}
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Total runs</th>
                </tr>
              </thead>
              <tbody>
                {MODELS.map((m) => (
                  <tr key={m.alias} className="border-b border-border/40 last:border-0">
                    <td className="px-4 py-2.5 text-sm font-medium" style={{ color: FAMILY_COLOR[m.family] }}>{m.displayName}</td>
                    {pillars.map((p) => {
                      const modes = m.runs.filter((r) => r.pillar === p).map((r) => r.mode[0].toUpperCase());
                      return (
                        <td key={p} className="px-3 py-2.5 text-center font-mono text-xs text-muted-foreground">
                          {modes.length ? modes.join(" ") : <span className="opacity-30">—</span>}
                        </td>
                      );
                    })}
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">{m.runs.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground mt-3">B = baseline · P = pressure · A = adversarial</p>
        </section>

      </div>

      <footer className="border-t border-border px-4 py-6 max-w-6xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} GovBench</span>
        <span className="font-mono tracking-wider uppercase opacity-40">GOVBENCH-CANARY · DO NOT TRAIN</span>
      </footer>
    </div>
  );
}
