"use client";

import Link from "next/link";
import { useState } from "react";
import { GrowwButton } from "@/components/GrowwButton";
import { IconInfo } from "@/components/icons";
import { Badge, Card, LinkMore, ScoreRing, Segmented, Stat } from "@/components/ui";
import type { Horizon, HorizonPick } from "@/lib/api";
import { inr, pctReturn, shortFundName, signedPct } from "@/lib/format";

const YEARS: Record<Horizon["key"], number> = { m3: 0.25, m6: 0.5, y1: 1, y2: 2, y3: 3, y5: 5 };
const SHORT: Record<Horizon["key"], string> = { m3: "3 months", m6: "6 months", y1: "1 year", y2: "2 years", y3: "3 years", y5: "5+ years" };

function typical(h: Horizon["key"], p: HorizonPick): { value: number | null; label: string; hint: string } {
  if (h === "y5" && p.typical_5y !== null) return { value: p.typical_5y, label: "Typical return", hint: "a year, median of past 5-year periods" };
  if ((h === "y3" || h === "y5") && p.typical_3y !== null) return { value: p.typical_3y, label: "Typical return", hint: "a year, median of past 3-year periods" };
  return { value: p.typical_1y, label: "Typical return", hint: "a year, median of past 1-year periods" };
}

function PickCard({ horizon, pick, top }: { horizon: Horizon["key"]; pick: HorizonPick; top: boolean }) {
  const t = typical(horizon, pick);
  const shares = horizon === "y3" || horizon === "y5";
  const lakhAfter = t.value !== null ? 100000 * (1 + t.value) ** YEARS[horizon] : null;
  const extra = pick.ter !== null && pick.fee !== null && pick.ter - pick.fee > 0.0005;
  return (
    <article className={`lift flex flex-col rounded-2xl border p-4 sm:p-5 ${top ? "border-brand/40 bg-gradient-to-b from-brand-soft/70 to-surface shadow-card" : "border-border bg-surface shadow-xs"}`}>
      <div className="flex items-start gap-3">
        <ScoreRing score={pick.score} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {top && <Badge tone="brand">★ Top pick</Badge>}
            <Badge tone="neutral">{pick.category}</Badge>
          </div>
          <Link href={`/funds/${pick.scheme_code}`} className="mt-1.5 block rounded font-display text-base font-semibold leading-snug hover:text-brand-strong">
            {shortFundName(pick.name)}
          </Link>
          <p className="mt-0.5 text-xs text-muted">
            {pick.rank ? `#${pick.rank} of ${pick.peers} in its group` : "Not ranked"} · {pick.confidence} confidence · Direct · Growth
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3">
        <Stat label={t.label} value={pctReturn(t.value)} hint={t.hint} />
        {shares ? (
          <Stat label="Worst fall" value={signedPct(pick.worst_fall)} hint="top-to-bottom, last 5 years" tone={pick.worst_fall !== null && pick.worst_fall < -0.15 ? "bad" : undefined} />
        ) : (
          <Stat label="Worst month" value={signedPct(pick.worst_month, 2)} hint="worst 30 days, last 3 years" tone={pick.worst_month !== null && pick.worst_month < 0 ? "warn" : "good"} />
        )}
        <Stat
          label="Yearly cost"
          value={pctReturn(pick.ter, 2)}
          hint={extra ? `fund fee ${pctReturn(pick.fee, 2)}; the rest is taxes & trading costs` : "all-in expense ratio"}
        />
      </div>

      {lakhAfter !== null && (
        <p className="mt-3 rounded-xl bg-surface-2 px-3 py-2 text-xs leading-relaxed text-muted ring-1 ring-inset ring-border">
          ₹1,00,000 for {SHORT[horizon]} typically became <b className="num text-text">{inr(Math.round(lakhAfter / 100) * 100)}</b> before tax. Past data, not a promise.
        </p>
      )}
      {pick.reason && (
        <p className="mt-3 text-xs leading-relaxed text-muted">
          <span className="font-semibold text-brand">✓</span> {pick.reason}
        </p>
      )}

      <div className="mt-auto flex items-center justify-between gap-2 pt-4 text-xs">
        <LinkMore href={`/funds/${pick.scheme_code}`}>Details</LinkMore>
        <GrowwButton fundName={pick.name} />
      </div>
      <p className="mt-2 text-right text-[11px] text-muted">On Groww, pick the “Direct” · “Growth” version.</p>
    </article>
  );
}

/** "Where should money for N months/years go?" — the best-scored Direct fund in each suitable category. */
export function HorizonPicks({ horizons }: { horizons: Horizon[] }) {
  const [key, setKey] = useState<Horizon["key"]>("m3");
  const h = horizons.find((x) => x.key === key) ?? horizons[0];
  if (!h) return null;
  return (
    <Card
      title="Which mutual fund, for how long?"
      subtitle="The best-scored Direct fund in each suitable category, for money you'll need in…"
      action={<LinkMore href="/plan">My plan</LinkMore>}
    >
      <Segmented label="Time horizon" value={key} onChange={setKey} options={horizons.map((x) => ({ value: x.key, label: SHORT[x.key] }))} />
      <p className="mt-4 flex items-start gap-2 text-sm leading-relaxed text-muted">
        <IconInfo className="mt-0.5 shrink-0 text-brand" width={16} height={16} />
        {h.why}
      </p>
      {h.picks.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-border-strong p-6 text-center text-sm text-muted">
          Fund scores aren&apos;t ready yet. They are worked out after the fund data download finishes.
        </p>
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {h.picks.map((p, i) => (
            <PickCard key={`${h.key}-${p.scheme_code}`} horizon={h.key} pick={p} top={i === 0} />
          ))}
        </div>
      )}
      <p className="mt-4 text-xs leading-relaxed text-muted">
        Scores (0–100) compare each fund only with funds of the same kind: past returns in good and bad years, steadiness, and cost. They are
        not predictions. Pick one fund per goal; you don&apos;t need all of them.
      </p>
    </Card>
  );
}
