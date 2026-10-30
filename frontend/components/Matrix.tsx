"use client";

import { useState } from "react";
import {
  STANCES,
  TIER_LABEL,
  cellsFor,
  data,
  findModel,
  humanize,
  pct,
  pooledBreakInterval,
  pooledRate,
  pressureAxis,
  roleAxis,
  type Summary,
} from "@/lib/data";

const STANCE_OPTIONS = [
  { value: "decision_maker", label: "Decision maker" },
  { value: "advisor", label: "Advisor" },
  { value: "both", label: "Both" },
];

/** Hue for a break rate: green at 0, red at 1. */
function hue(rate: number): number {
  return 155 - 128 * rate;
}

/** Row of buttons with one active option. */
function Choice({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={`h-8 px-3 text-sm rounded-md border transition-colors ${
              active
                ? "bg-foreground text-background border-foreground"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** One matrix cell: break rate large, bend and escalate small, and n. */
function Cell({ cells }: { cells: Summary[] }) {
  const brk = pooledRate(cells, "break");
  const n = cells.reduce((total, c) => total + c.n, 0);
  const unresolved = cells.reduce((total, c) => total + c.unresolved, 0);
  const interval = pooledBreakInterval(cells);
  if (brk === null) return (
    <td className="px-4 py-3 text-muted-foreground">
      <div>No settled results</div>
      <div className="mt-1 text-xs">n=0 · unresolved {unresolved}</div>
    </td>
  );
  const h = hue(brk);
  return (
    <td className="px-4 py-3 align-top" style={{ background: `oklch(70% 0.16 ${h} / 0.12)` }}>
      <div className="font-mono text-2xl font-semibold" style={{ color: `oklch(80% 0.15 ${h})` }}>
        {pct(brk)}
      </div>
      <div className="mt-1 font-mono text-xs text-muted-foreground">
        bend {pct(pooledRate(cells, "bend"))} · escalate {pct(pooledRate(cells, "escalate"))} · n={n}
      </div>
      <div className="mt-1 font-mono text-xs text-muted-foreground">
        {interval && <>95% CI {pct(interval[0])}–{pct(interval[1])} · </>}
        unresolved {unresolved}
      </div>
    </td>
  );
}

/** Break-rate grid for one model: pressures down, roles across, with model and stance pickers. */
export default function Matrix() {
  const [alias, setAlias] = useState(data.models[0]?.alias ?? "");
  const [stance, setStance] = useState("both");
  const [tier, setTier] = useState(data.tiers[0] ?? "standard");
  const model = findModel(alias);
  if (!model) return <p className="text-sm text-muted-foreground">No model results yet.</p>;

  const roles = roleAxis();
  const pressures = pressureAxis();
  const stances = stance === "both" ? STANCES : [stance];

  return (
    <div className="space-y-4">
      <Choice
        options={data.models.map((m) => ({ value: m.alias, label: m.name }))}
        value={alias}
        onChange={setAlias}
      />
      {data.tiers.length > 1 && (
        <Choice
          options={data.tiers.map((t) => ({ value: t, label: TIER_LABEL[t] ?? t }))}
          value={tier}
          onChange={setTier}
        />
      )}
      <Choice options={STANCE_OPTIONS} value={stance} onChange={setStance} />

      <div className="border border-border bg-card rounded-md overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40">
              <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Pressure</th>
              {roles.map((role) => (
                <th key={role} className="text-left px-4 py-3 text-xs font-medium text-muted-foreground first-letter:uppercase">
                  {humanize(role)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pressures.map((pressure) => (
              <tr key={pressure} className="border-b border-border/40 last:border-0">
                <th scope="row" className="px-4 py-3 text-left text-xs font-medium text-foreground whitespace-nowrap first-letter:uppercase">
                  {humanize(pressure)}
                </th>
                {roles.map((role) => (
                  <Cell key={role} cells={cellsFor(tier, model.alias, role, pressure, stances)} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed max-w-[72ch]">
        Break is BREAK plus BREAK_RATIONALIZED. Bend and escalate are in small print. Green is 0%,
        red is 100%. Both pools the two stances. n counts the episodes behind each rate. Hard
        cases have grey facts and pressure that sounds reasonable. Intervals are descriptive Wilson
        intervals and do not account for repeated scenarios. Unresolved episodes are excluded from n.
      </p>
    </div>
  );
}
