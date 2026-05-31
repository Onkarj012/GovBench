import Link from "next/link";
import Nav from "@/components/Nav";
import { getLeaderboard, PILLARS, PillarKey, FAMILY_COLOR, GRADE_COLOR, gradeFromScore } from "@/lib/data";

const X_AXIS = [0, 25, 50, 75, 100];

export default function Home() {
  const leaderboard = getLeaderboard();
  const pillars = Object.keys(PILLARS) as PillarKey[];

  return (
    <div className="min-h-screen bg-background text-foreground">

      <Nav />

      <main className="max-w-6xl mx-auto px-4 py-8">

        {/* ── Hero ── */}
        <section className="py-12">
          <h1 className="text-5xl font-semibold tracking-tight text-foreground mb-3">
            GovBench
          </h1>
          <p className="text-muted-foreground text-lg max-w-[60ch] leading-relaxed mb-6">
            Institutional Readiness &amp; Bias Benchmark for Governance — evaluating AI language
            models for demographic bias and governance readiness across 6 pillars.
          </p>
          <div className="flex items-center gap-3">
            <a href="#leaderboard"
              className="inline-flex items-center gap-1.5 bg-foreground text-background px-4 h-10 text-sm font-medium hover:bg-foreground/85 transition-colors rounded-md">
              View Leaderboard
            </a>
            <a href="https://github.com/onkarj012/irbg"
              className="inline-flex items-center gap-1.5 border border-border px-4 h-10 text-sm hover:bg-muted/40 transition-colors rounded-md">
              GitHub
            </a>
          </div>
        </section>

        {/* ── Leaderboard ── */}
        <section id="leaderboard" className="py-8">
          <div className="flex items-baseline gap-3 mb-6">
            <h2 className="text-xl font-semibold tracking-tight">Leaderboard</h2>
            <span className="text-sm text-muted-foreground">Models ({leaderboard.length})</span>
          </div>

          {/* Bar chart */}
          <div className="border border-border bg-card rounded-md mb-8">
            <div className="p-6">
              {/* Bars */}
              <div className="space-y-2.5 mb-3">
                {leaderboard.map((model, i) => {
                  const grade = gradeFromScore(model.composite);
                  const familyColor = FAMILY_COLOR[model.family];
                  const gradeColor = GRADE_COLOR[grade];
                  return (
                    <Link key={model.alias} href={`/model/${model.alias}`}
                      className="flex items-center gap-3 group">
                      <span className="w-4 text-right text-xs text-muted-foreground shrink-0 font-mono">{i + 1}</span>
                      <span className="w-40 text-sm truncate shrink-0 transition-colors group-hover:text-foreground"
                        style={{ color: familyColor }}>
                        {model.displayName}
                      </span>
                      {/* bar track */}
                      <div className="flex-1 relative h-6 rounded-sm overflow-hidden bg-muted">
                        <div className="h-full transition-all duration-300"
                          style={{ width: `${model.composite}%`, background: familyColor, opacity: 0.85 }} />
                      </div>
                      <span className="w-16 text-right text-xs font-mono text-muted-foreground shrink-0">
                        {model.composite.toFixed(1)}%
                      </span>
                      <span className="w-5 text-xs font-semibold shrink-0 font-mono"
                        style={{ color: gradeColor }}>
                        {grade}
                      </span>
                    </Link>
                  );
                })}
              </div>
              {/* X-axis */}
              <div className="flex ml-[calc(1rem+0.75rem+10rem+0.75rem)] mr-[calc(4rem+0.75rem+1.25rem+0.75rem)]">
                {X_AXIS.map((v) => (
                  <span key={v} className="flex-1 text-xs text-muted-foreground font-mono first:text-left last:text-right text-center">
                    {v}%
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Table */}
          <div className="border border-border bg-card rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  <th className="text-left px-4 py-3 text-muted-foreground font-medium text-xs w-8">#</th>
                  <th className="text-left px-4 py-3 text-muted-foreground font-medium text-xs">Model</th>
                  <th className="text-right px-4 py-3 text-muted-foreground font-medium text-xs">Score</th>
                  <th className="text-center px-4 py-3 text-muted-foreground font-medium text-xs">Grade</th>
                  {pillars.map((p) => (
                    <th key={p} className="text-right px-3 py-3 text-muted-foreground font-medium text-xs">
                      {p.split("_")[0].toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((model, i) => {
                  const grade = gradeFromScore(model.composite);
                  const gradeColor = GRADE_COLOR[grade];
                  const familyColor = FAMILY_COLOR[model.family];
                  return (
                    <tr key={model.alias} className="border-b border-border/40 last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 text-muted-foreground text-xs font-mono">{i + 1}</td>
                      <td className="px-4 py-3">
                        <Link href={`/model/${model.alias}`}
                          className="font-medium hover:text-foreground transition-colors"
                          style={{ color: familyColor }}>
                          {model.displayName}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-foreground">
                        {model.composite.toFixed(1)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className="text-xs font-semibold font-mono" style={{ color: gradeColor }}>{grade}</span>
                      </td>
                      {pillars.map((p) => {
                        const s = model.pillarScores[p];
                        const pg = s !== undefined ? gradeFromScore(s) : "F";
                        return (
                          <td key={p} className="px-3 py-3 text-right font-mono text-xs">
                            {s !== undefined
                              ? <span style={{ color: GRADE_COLOR[pg] }}>{s.toFixed(0)}</span>
                              : <span className="text-muted-foreground">—</span>}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Pillars ── */}
        <section id="pillars" className="py-8">
          <h2 className="text-xl font-semibold tracking-tight mb-6">Evaluation Pillars</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {pillars.map((p) => (
              <div key={p} className="border border-border bg-card rounded-md p-4">
                <div className="text-xs font-mono text-muted-foreground mb-1 tracking-wider uppercase">
                  {p.split("_")[0]}
                </div>
                <div className="text-sm font-medium text-foreground">
                  {PILLARS[p].replace(/^P\d+: /, "")}
                </div>
              </div>
            ))}
          </div>
        </section>

      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-border px-4 py-6 max-w-6xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} GovBench</span>
        <span className="font-mono tracking-wider uppercase opacity-40">
          GOVBENCH-CANARY · DO NOT TRAIN
        </span>
      </footer>
    </div>
  );
}
