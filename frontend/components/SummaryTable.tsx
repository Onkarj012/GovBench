import type { ReactNode } from "react";
import { pct, type Summary } from "@/lib/data";

/** One table row: a label, an optional extra cell, and the summary to show. */
export interface SummaryRow {
  key: string;
  label: ReactNode;
  extra?: ReactNode;
  summary: Summary;
}

const TH = "px-3 py-3 text-right text-xs font-medium text-muted-foreground whitespace-nowrap";
const TD = "px-3 py-3 text-right font-mono text-xs whitespace-nowrap";

/** Rates table: one row per slice, with break, bend, escalate, refuse, and n. */
export default function SummaryTable({
  labelHead,
  extraHead,
  rows,
}: {
  labelHead: string;
  extraHead?: string;
  rows: SummaryRow[];
}) {
  return (
    <div className="border border-border bg-card rounded-md overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/40">
            <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground whitespace-nowrap">
              {labelHead}
            </th>
            {extraHead && (
              <th className="text-left px-3 py-3 text-xs font-medium text-muted-foreground whitespace-nowrap">
                {extraHead}
              </th>
            )}
            <th className={TH}>Break</th>
            <th className={TH}>Bend</th>
            <th className={TH}>Escalate</th>
            <th className={TH}>Refuse</th>
            <th className={TH}>Turn-0 accuracy</th>
            <th className={TH}>Median turns to break</th>
            <th className={TH}>Rationalized</th>
            <th className={TH}>Unresolved</th>
            <th className={TH}>n</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, label, extra, summary: s }) => (
            <tr key={key} className="border-b border-border/40 last:border-0 hover:bg-muted/30 transition-colors">
              <td className="px-4 py-3 text-sm first-letter:uppercase">{label}</td>
              {extraHead && (
                <td className="px-3 py-3 font-mono text-xs text-muted-foreground whitespace-nowrap">{extra}</td>
              )}
              <td className={TD}>
                <div className="text-sm font-semibold text-foreground">{pct(s.break.rate)}</div>
                {s.break.ci && (
                  <div className="text-xs text-muted-foreground">
                    {pct(s.break.ci[0])}–{pct(s.break.ci[1])}
                  </div>
                )}
              </td>
              <td className={TD}>{pct(s.bend.rate)}</td>
              <td className={TD}>{pct(s.escalate.rate)}</td>
              <td className={TD}>{pct(s.refuse.rate)}</td>
              <td className={TD}>{pct(s.turn0_accuracy)}</td>
              <td className={TD}>{s.median_turns_to_break ?? "—"}</td>
              <td className={TD}>{pct(s.rationalized_share)}</td>
              <td className={TD}>{s.unresolved}</td>
              <td className={TD}>{s.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
