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
            All benchmark runs, confidence intervals, robustness deltas, parity gaps, and coverage data.
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
                  {["Model", "Mode", "Pillar", "Score", "Parity Gap", "Grade", "Latency", "Tokens", "Flags"].map((h, i) => (
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
                        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">
                          {r.parity_gap !== undefined ? (
                            <span style={{ color: r.parity_gap > 15 ? GRADE_COLOR["F"] : r.parity_gap > 5 ? GRADE_COLOR["D"] : GRADE_COLOR["A"] }}>
                              {r.parity_gap.toFixed(1)}
                            </span>
                          ) : "—"}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-xs font-semibold" style={{ color: GRADE_COLOR[g] }}>{g}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">{(r.avg_latency_ms / 1000).toFixed(1)}s</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">{r.avg_tokens.toFixed(0)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs">
                          {r.judge_disagreement && <span className="text-yellow-500">⚠ disagree</span>}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground mt-3">Parity Gap = share of demographic variants with divergent decision (P1 only). Lower is better.</p>
        </section>

        {/* ── Confidence Intervals ── */}
        <section>
          <h2 className="text-xl font-semibold tracking-tight mb-1">95% Confidence Intervals</h2>
          <p className="text-sm text-muted-foreground mb-5">
            Bootstrap 95% CI per pillar (baseline mode). Wide intervals indicate few repeat runs — results are directional.
          </p>
          <div className="border border-border bg-card rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  {["Model", "Pillar", "N", "Mean", "CI Low", "CI High", "±"].map((h, i) => (
                    <th key={h} className={`px-4 py-2.5 text-muted-foreground font-medium text-xs ${i >= 2 ? "text-right" : "text-left"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MODELS.flatMap((m) =>
                  (m.pillarCI ?? []).map((ci) => {
                    const width = ci.ci_high - ci.ci_low;
                    return (
                      <tr key={`${m.alias}-${ci.pillar}`} className="border-b border-border/40 last:border-0 hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-2 text-sm font-medium" style={{ color: FAMILY_COLOR[m.family] }}>{m.displayName}</td>
                        <td className="px-4 py-2 text-xs text-muted-foreground">{PILLARS[ci.pillar]}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">{ci.n}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs" style={{ color: GRADE_COLOR[gradeFromScore(ci.mean)] }}>{ci.mean.toFixed(1)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">{ci.ci_low.toFixed(1)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">{ci.ci_high.toFixed(1)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs" style={{ color: width > 20 ? GRADE_COLOR["F"] : GRADE_COLOR["A"] }}>
                          ±{(width / 2).toFixed(1)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Robustness Delta ── */}
        <section>
          <h2 className="text-xl font-semibold tracking-tight mb-1">Robustness Delta</h2>
          <p className="text-sm text-muted-foreground mb-5">
            Baseline − pressure per pillar. Positive = score degraded under pressure.
          </p>
          <div className="border border-border bg-card rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  {["Model", "Pillar", "Baseline", "Pressure", "Δ"].map((h, i) => (
                    <th key={h} className={`px-4 py-2.5 text-muted-foreground font-medium text-xs ${i >= 2 ? "text-right" : "text-left"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MODELS.flatMap((m) =>
                  (m.robustness ?? []).map((r) => {
                    const deltaColor = r.delta > 10 ? GRADE_COLOR["F"] : r.delta > 3 ? GRADE_COLOR["D"] : r.delta < -3 ? GRADE_COLOR["A"] : "inherit";
                    return (
                      <tr key={`${m.alias}-${r.pillar}`} className="border-b border-border/40 last:border-0 hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-2 text-sm font-medium" style={{ color: FAMILY_COLOR[m.family] }}>{m.displayName}</td>
                        <td className="px-4 py-2 text-xs text-muted-foreground">{PILLARS[r.pillar]}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs" style={{ color: GRADE_COLOR[gradeFromScore(r.baseline)] }}>{r.baseline.toFixed(1)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs" style={{ color: GRADE_COLOR[gradeFromScore(r.pressure)] }}>{r.pressure.toFixed(1)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs font-semibold" style={{ color: deltaColor }}>
                          {r.delta >= 0 ? "+" : ""}{r.delta.toFixed(1)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Per-pillar rankings ── */}
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
                    {rows.length === 0 && <p className="text-xs text-muted-foreground px-1">No data</p>}
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
        </section>

        {/* ── Run coverage ── */}
        <section>
          <h2 className="text-xl font-semibold tracking-tight mb-1">Run Coverage</h2>
          <p className="text-sm text-muted-foreground mb-5">
            Which pillars and modes have been run. Coverage ratio = runs completed / 18 required cells.
          </p>
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
                  <th className="text-right px-4 py-2.5 text-muted-foreground font-medium text-xs">Coverage</th>
                </tr>
              </thead>
              <tbody>
                {MODELS.map((m) => {
                  const pct = Math.round((m.coverageRatio ?? 0) * 100);
                  const coverageColor = pct >= 80 ? GRADE_COLOR["A"] : pct >= 50 ? GRADE_COLOR["C"] : GRADE_COLOR["F"];
                  return (
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
                      <td className="px-4 py-2.5 text-right font-mono text-xs font-semibold" style={{ color: coverageColor }}>
                        {pct}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground mt-3">B = baseline · P = pressure · A = adversarial · Coverage = runs / 18 required cells</p>
        </section>

      </div>

      <footer className="border-t border-border px-4 py-6 max-w-6xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} GovBench</span>
        <span className="font-mono tracking-wider uppercase opacity-40">GOVBENCH-CANARY · DO NOT TRAIN</span>
      </footer>
    </div>
  );
}
