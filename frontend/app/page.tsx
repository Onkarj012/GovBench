import Link from "next/link";
import Nav from "@/components/Nav";
import {
  getLeaderboard,
  PILLARS,
  PillarKey,
  Grade,
  FAMILY_COLOR,
  GRADE_COLOR,
  gradeFromScore,
} from "@/lib/data";

const X_AXIS = [0, 25, 50, 75, 100];
const GITHUB = "https://github.com/Onkarj012/GovBench";

function GradePill({ grade, muted }: { grade: Grade; muted?: boolean }) {
  const c = GRADE_COLOR[grade];
  return (
    <span
      className="inline-flex items-center justify-center w-6 h-5 rounded text-xs font-semibold font-mono"
      style={{
        color: c,
        background: `color-mix(in oklch, ${c} 15%, transparent)`,
        opacity: muted ? 0.4 : 1,
      }}
    >
      {grade}
    </span>
  );
}

function coverageColor(pct: number): string {
  return pct >= 80
    ? GRADE_COLOR.A
    : pct >= 50
      ? GRADE_COLOR.C
      : GRADE_COLOR.F;
}

export default function Home() {
  const pillars = Object.keys(PILLARS) as PillarKey[];
  // Rank complete models (all 6 pillars scored) first — a composite grade is
  // only comparable when every pillar is present.
  const ranked = [...getLeaderboard()].sort((a, b) => {
    const ca = Object.keys(a.pillarScores).length === pillars.length ? 1 : 0;
    const cb = Object.keys(b.pillarScores).length === pillars.length ? 1 : 0;
    return cb - ca || b.composite - a.composite;
  });
  const hasPartial = ranked.some(
    (m) => Object.keys(m.pillarScores).length < pillars.length,
  );

  const stats = [
    { label: "Models", value: ranked.length },
    { label: "Pillars", value: pillars.length },
    { label: "Jurisdictions", value: 3 },
    { label: "Run modes", value: 3 },
  ];

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
            Institutional Readiness &amp; Bias Benchmark for Governance —
            evaluating AI language models for demographic bias and governance
            readiness across 6 pillars.
          </p>
          <div className="flex items-center gap-3">
            <a
              href="#leaderboard"
              className="inline-flex items-center gap-1.5 bg-foreground text-background px-4 h-10 text-sm font-medium hover:bg-foreground/85 transition-colors rounded-md"
            >
              View Leaderboard
            </a>
            <a
              href={GITHUB}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 border border-border px-4 h-10 text-sm hover:bg-muted/40 transition-colors rounded-md"
            >
              GitHub ↗
            </a>
          </div>

          {/* Stats strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-10">
            {stats.map((s) => (
              <div
                key={s.label}
                className="border border-border bg-card rounded-md px-4 py-3"
              >
                <div className="text-2xl font-semibold font-mono text-foreground">
                  {s.value}
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── Leaderboard ── */}
        <section id="leaderboard" className="py-8">
          <div className="flex items-baseline gap-3 mb-6">
            <h2 className="text-xl font-semibold tracking-tight">Leaderboard</h2>
            <span className="text-sm text-muted-foreground">
              Models ({ranked.length})
            </span>
          </div>

          {/* Bar chart */}
          <div className="border border-border bg-card rounded-md mb-8">
            <div className="p-6">
              <div className="space-y-2.5 mb-3">
                {ranked.map((model, i) => {
                  const grade = gradeFromScore(model.composite);
                  const familyColor = FAMILY_COLOR[model.family];
                  const complete =
                    Object.keys(model.pillarScores).length === pillars.length;
                  return (
                    <Link
                      key={model.alias}
                      href={`/model/${model.alias}`}
                      className="flex items-center gap-3 group"
                    >
                      <span className="w-4 text-right text-xs text-muted-foreground shrink-0 font-mono">
                        {i + 1}
                      </span>
                      <span
                        className="w-40 text-sm truncate shrink-0 transition-colors group-hover:text-foreground"
                        style={{ color: familyColor }}
                      >
                        {model.displayName}
                        {!complete && (
                          <span className="text-muted-foreground">&nbsp;*</span>
                        )}
                      </span>
                      <div className="flex-1 relative h-6 rounded-sm overflow-hidden bg-muted">
                        <div
                          className="h-full transition-all duration-300"
                          style={{
                            width: `${model.composite}%`,
                            background: familyColor,
                            opacity: complete ? 0.85 : 0.4,
                          }}
                        />
                      </div>
                      <span className="w-16 text-right text-xs font-mono text-muted-foreground shrink-0">
                        {model.composite.toFixed(1)}%
                      </span>
                      <span className="w-6 shrink-0 flex justify-end">
                        <GradePill grade={grade} muted={!complete} />
                      </span>
                    </Link>
                  );
                })}
              </div>
              {/* X-axis */}
              <div className="flex ml-[calc(1rem+0.75rem+10rem+0.75rem)] mr-[calc(4rem+0.75rem+1.5rem+0.75rem)]">
                {X_AXIS.map((v) => (
                  <span
                    key={v}
                    className="flex-1 text-xs text-muted-foreground font-mono first:text-left last:text-right text-center"
                  >
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
                  <th className="text-left px-4 py-3 text-muted-foreground font-medium text-xs w-8">
                    #
                  </th>
                  <th className="text-left px-4 py-3 text-muted-foreground font-medium text-xs">
                    Model
                  </th>
                  <th className="text-right px-4 py-3 text-muted-foreground font-medium text-xs">
                    Score
                  </th>
                  <th className="text-center px-4 py-3 text-muted-foreground font-medium text-xs">
                    Grade
                  </th>
                  <th className="text-right px-4 py-3 text-muted-foreground font-medium text-xs">
                    Coverage
                  </th>
                  {pillars.map((p) => (
                    <th
                      key={p}
                      className="text-right px-3 py-3 text-muted-foreground font-medium text-xs"
                    >
                      {p.split("_")[0].toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ranked.map((model, i) => {
                  const grade = gradeFromScore(model.composite);
                  const familyColor = FAMILY_COLOR[model.family];
                  const complete =
                    Object.keys(model.pillarScores).length === pillars.length;
                  const pct = Math.round((model.coverageRatio ?? 0) * 100);
                  return (
                    <tr
                      key={model.alias}
                      className="border-b border-border/40 last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3 text-muted-foreground text-xs font-mono">
                        {i + 1}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/model/${model.alias}`}
                          className="font-medium hover:text-foreground transition-colors"
                          style={{ color: familyColor }}
                        >
                          {model.displayName}
                        </Link>
                        {!complete && (
                          <span className="text-muted-foreground text-xs">
                            &nbsp;*
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-foreground">
                        {model.composite.toFixed(1)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-center">
                          <GradePill grade={grade} muted={!complete} />
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 rounded-sm bg-muted overflow-hidden">
                            <div
                              className="h-full"
                              style={{
                                width: `${pct}%`,
                                background: coverageColor(pct),
                              }}
                            />
                          </div>
                          <span className="text-xs font-mono text-muted-foreground w-8 text-right">
                            {pct}%
                          </span>
                        </div>
                      </td>
                      {pillars.map((p) => {
                        const s = model.pillarScores[p];
                        const pg = s !== undefined ? gradeFromScore(s) : "F";
                        return (
                          <td
                            key={p}
                            className="px-3 py-3 text-right font-mono text-xs"
                          >
                            {s !== undefined ? (
                              <span style={{ color: GRADE_COLOR[pg] }}>
                                {s.toFixed(0)}
                              </span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {hasPartial && (
            <p className="text-xs text-muted-foreground mt-3">
              * Partial coverage — not all 6 pillars scored, so the composite
              and grade are indicative only.
            </p>
          )}
        </section>

        {/* ── Pillars ── */}
        <section id="pillars" className="py-8">
          <h2 className="text-xl font-semibold tracking-tight mb-6">
            Evaluation Pillars
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {pillars.map((p) => (
              <div
                key={p}
                className="border border-border bg-card rounded-md p-4"
              >
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
