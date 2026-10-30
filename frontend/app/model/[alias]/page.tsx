import { notFound } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import SummaryTable, { type SummaryRow } from "@/components/SummaryTable";
import {
  TIER_LABEL,
  data,
  findModel,
  humanize,
  pct,
  type ModelManifest,
  type Summary,
} from "@/lib/data";

/** Builds one static page per model in the data file. */
export function generateStaticParams() {
  return data.models.map((m) => ({ alias: m.alias }));
}

/** Table rows for one breakdown, in file order. */
function rowsOf(breakdown: Partial<Record<string, Summary>>): SummaryRow[] {
  return Object.entries(breakdown).flatMap(([key, summary]) =>
    summary ? [{ key, label: humanize(key), summary }] : [],
  );
}

/** One model: overall summary, then breakdowns by stance, role, and pressure. */
export default async function ModelPage({ params }: { params: Promise<{ alias: string }> }) {
  const { alias } = await params;
  const model = findModel(alias);
  if (!model) notFound();

  const manifest: ModelManifest | undefined = data.manifest.models[alias];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Nav />

      <main className="max-w-6xl mx-auto px-4 py-8 space-y-10">

        {/* ── Header ── */}
        <div className="pt-6 pb-4 border-b border-border/40">
          <Link href="/" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
            All models
          </Link>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight">{model.name}</h1>
          {manifest && (
            <p className="mt-2 font-mono text-sm text-muted-foreground">
              {model.alias} · {manifest.backend} · {manifest.model_id} · seeds {manifest.seeds} · temperature{" "}
              {manifest.temperature ?? "default"}
            </p>
          )}
        </div>

        {Object.entries(model.tiers).map(([tier, t]) => t && (
          <div key={tier} className="space-y-8">
            <h2 className="text-2xl font-semibold tracking-tight">{TIER_LABEL[tier] ?? tier} cases</h2>

            <section>
              <h3 className="text-lg font-semibold tracking-tight mb-4">Summary</h3>
              <SummaryTable
                labelHead="Scope"
                rows={[{ key: "all", label: "All episodes", summary: t.summary }]}
              />
              {t.control && (
                <p className="mt-3 text-sm text-muted-foreground">
                  Follows new facts: {pct(t.control.updated.rate)} of {t.control.n} control
                  episodes changed the decision when a neutral source added a legally relevant fact.
                </p>
              )}
            </section>

            <section>
              <h3 className="text-lg font-semibold tracking-tight mb-4">By stance</h3>
              <SummaryTable labelHead="Stance" rows={rowsOf(t.by_stance)} />
            </section>

            <section>
              <h3 className="text-lg font-semibold tracking-tight mb-4">By role</h3>
              <SummaryTable labelHead="Role" rows={rowsOf(t.by_role)} />
            </section>

            <section>
              <h3 className="text-lg font-semibold tracking-tight mb-4">By pressure</h3>
              <SummaryTable labelHead="Pressure" rows={rowsOf(t.by_pressure)} />
            </section>
          </div>
        ))}

      </main>

      <footer className="border-t border-border px-4 py-6 max-w-6xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} GovBench</span>
        <span className="font-mono tracking-wider uppercase opacity-40">GOVBENCH-CANARY · DO NOT TRAIN</span>
      </footer>
    </div>
  );
}
