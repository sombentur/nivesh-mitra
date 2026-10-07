"use client";

import { useState } from "react";
import type { Split } from "@/lib/api";

export const BUCKETS = [
  { key: "core", label: "Mutual funds (core)", short: "Mutual funds", color: "var(--series-1)", hint: "SIPs in 3–5 funds — the largest, steadiest part." },
  { key: "satellite", label: "Direct stocks (satellite)", short: "Stocks", color: "var(--series-2)", hint: "Long-term stock picks, held 1+ years." },
  { key: "trading", label: "Short-term trading", short: "Trading", color: "var(--series-3)", hint: "Small, capped bucket for short-term ideas." },
] as const;

/** Part-to-whole bar for the 3-bucket split, with a legend that doubles as the data table. */
export function AllocationBar({ split, caption }: { split: Split; caption?: string }) {
  const [hover, setHover] = useState<string | null>(null);
  const parts = BUCKETS.filter((b) => split[b.key] > 0);
  const active = BUCKETS.find((b) => b.key === hover);

  return (
    <figure className="grid gap-3">
      <div className="relative">
        <div className="flex h-3.5 w-full gap-[2px]" role="img" aria-label={BUCKETS.map((b) => `${b.label} ${split[b.key]}%`).join(", ")}>
          {parts.map((b, i) => (
            <div
              key={b.key}
              onMouseEnter={() => setHover(b.key)}
              onMouseLeave={() => setHover(null)}
              className={`h-full transition-opacity duration-200 ${i === 0 ? "rounded-l-full" : ""} ${i === parts.length - 1 ? "rounded-r-full" : ""} ${hover && hover !== b.key ? "opacity-40" : ""}`}
              style={{ width: `${split[b.key]}%`, background: b.color }}
            />
          ))}
        </div>
        {active && (
          <div className="glass pointer-events-none absolute -top-10 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg border border-border px-2.5 py-1 text-xs">
            <b>{split[active.key]}%</b> {active.label}
          </div>
        )}
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
        {BUCKETS.map((b) => (
          <li key={b.key} className="flex items-center gap-2 whitespace-nowrap" onMouseEnter={() => setHover(b.key)} onMouseLeave={() => setHover(null)}>
            <span className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: b.color }} />
            <span className="text-muted">{b.short}</span>
            <span className="num font-semibold">{split[b.key]}%</span>
          </li>
        ))}
      </ul>
      {caption && <figcaption className="text-xs text-muted">{caption}</figcaption>}
    </figure>
  );
}
