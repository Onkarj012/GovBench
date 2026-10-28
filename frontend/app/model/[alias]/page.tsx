import { notFound } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import SummaryTable, { type SummaryRow } from "@/components/SummaryTable";
import {
  data,
  findModel,
  humanize,
  type ModelManifest,
  type Summary,
} from "@/lib/data";

/** Builds one static page per model in the data file. */
export function generateStaticParams() {
  return data.models.map((m) => ({ alias: m.alias }));
}

/** Table rows for one breakdown, in file order. */
function rowsOf(breakdown: Record<string, Summary>): SummaryRow[] {
  return Object.entries(breakdown).map(([key, summary]) => ({
    key,
    label: humanize(key),
    summary,
  }));
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

        <section>
          <h2 className="text-lg font-semibold tracking-tight mb-4">Summary</h2>
          <SummaryTable
            labelHead="Scope"
            rows={[{ key: "all", label: "All episodes", summary: model.summary }]}
          />
        </section>

        <section>
          <h2 className="text-lg font-semibold tracking-tight mb-4">By stance</h2>
          <SummaryTable labelHead="Stance" rows={rowsOf(model.by_stance)} />
        </section>

        <section>
          <h2 className="text-lg font-semibold tracking-tight mb-4">By role</h2>
          <SummaryTable labelHead="Role" rows={rowsOf(model.by_role)} />
        </section>

        <section>
          <h2 className="text-lg font-semibold tracking-tight mb-4">By pressure</h2>
          <SummaryTable labelHead="Pressure" rows={rowsOf(model.by_pressure)} />
        </section>

      </main>

      <footer className="border-t border-border px-4 py-6 max-w-6xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} GovBench</span>
        <span className="font-mono tracking-wider uppercase opacity-40">GOVBENCH-CANARY · DO NOT TRAIN</span>
      </footer>
    </div>
  );
}
