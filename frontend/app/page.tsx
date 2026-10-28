import Link from "next/link";
import Nav from "@/components/Nav";
import Matrix from "@/components/Matrix";
import SummaryTable from "@/components/SummaryTable";
import { TIER_LABEL, data, formatIST, pct } from "@/lib/data";

/** Home: headline, explainer, draft banner, role x pressure matrix, and model summary. */
export default function Home() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Nav active="Matrix" />

      <main className="max-w-6xl mx-auto px-4 py-8">

        {/* ── Hero ── */}
        <section className="pt-10 pb-8">
          <p className="text-xs font-mono text-muted-foreground tracking-wider uppercase mb-4">
            GovBench v2 · India · run {data.run_name} · {data.manifest.scenario_count} scenarios ·{" "}
            {formatIST(data.generated_at)}
          </p>
          <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight mb-4 max-w-[24ch]">
            What does an AI do when the minister calls?
          </h1>
          <p className="text-muted-foreground text-lg max-w-[60ch] leading-relaxed">
            GovBench puts a model in an Indian public office with a real decision, such as bail, a
            tender award, or land acquisition. It then applies pressure over several turns: a
            superior&apos;s order, a bribe, a deadline, a sympathetic litigant. Each episode is
            classed as hold, bend, break, refuse, or escalate. Results are rates by role and by
            pressure. There is no composite score.
          </p>
        </section>

        {data.include_draft && (
          <p role="note"
            className="mb-8 border border-border border-l-2 border-l-grade-c bg-card rounded-md px-4 py-3 text-sm text-muted-foreground">
            v2 preview: scenarios are drafts cited to primary sources and not yet reviewed by a lawyer.
          </p>
        )}
        <p className="mb-8 text-sm text-muted-foreground max-w-[72ch]">
          Models on the <code className="font-mono text-xs">codex</code> and{" "}
          <code className="font-mono text-xs">claude_code</code> backends run as served through those
          CLIs, which add their own system prompt on top of the role prompt.
        </p>

        {/* ── Matrix ── */}
        <section id="matrix" className="py-8">
          <h2 className="text-xl font-semibold tracking-tight mb-4">Break rate by role and pressure</h2>
          <Matrix />
        </section>

        {/* ── Models, one table per tier ── */}
        {data.tiers.map((tier) => {
          const models = data.models.filter((m) => m.tiers[tier]);
          const hasControl = models.some((m) => m.tiers[tier].control);
          return (
            <section key={tier} id={`models-${tier}`} className="py-8">
              <div className="flex items-baseline gap-3 mb-4">
                <h2 className="text-xl font-semibold tracking-tight">
                  Models · {TIER_LABEL[tier] ?? tier} cases
                </h2>
                <span className="text-sm text-muted-foreground">{models.length}</span>
              </div>
              <SummaryTable
                labelHead="Model"
                extraHead={hasControl ? "Follows new facts" : "Backend"}
                rows={models.map((m) => {
                  const control = m.tiers[tier].control;
                  return {
                    key: m.alias,
                    label: (
                      <Link href={`/model/${m.alias}`} className="hover:underline underline-offset-4">
                        {m.name}
                      </Link>
                    ),
                    extra: hasControl
                      ? control
                        ? `${pct(control.updated.rate)} of ${control.n}`
                        : "—"
                      : m.backend,
                    summary: m.tiers[tier].summary,
                  };
                })}
              />
              {hasControl && (
                <p className="mt-3 text-xs text-muted-foreground max-w-[72ch] leading-relaxed">
                  Follows new facts: in separate control episodes, a neutral source adds one new,
                  legally relevant fact that should change the decision. A model that resists
                  pressure but also ignores real facts is stubborn, not principled.
                </p>
              )}
            </section>
          );
        })}

      </main>

      <footer className="border-t border-border px-4 py-6 max-w-6xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} GovBench</span>
        <span className="font-mono tracking-wider uppercase opacity-40">
          GOVBENCH-CANARY · DO NOT TRAIN
        </span>
      </footer>
    </div>
  );
}
