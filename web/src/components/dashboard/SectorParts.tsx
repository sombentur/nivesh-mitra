"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { growwSearchUrl } from "@/components/GrowwButton";
import { Sparkline } from "@/components/Sparkline";
import { ChangePill } from "@/components/dashboard/MarketWidgets";
import { Badge, Delta } from "@/components/ui";
import type { MarketStock, SectorSummary } from "@/lib/api";
import { fmtDate, signedPct } from "@/lib/format";

export const price = (n: number) => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const TREND_TONE = { Uptrend: "good", Downtrend: "bad", Sideways: "neutral", New: "neutral" } as const;

/** "Close of 1 Oct" or "Live · updated 11:05 am", for a sector response. */
export function asOfNote(d: { live: boolean; updated_at: string; as_of: string | null }) {
  return d.live ? `Live · updated ${new Date(d.updated_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}` : d.as_of ? `Close of ${fmtDate(d.as_of)}` : "";
}

/** Up / down split of a sector's companies as one thin bar. */
export function UpDownBar({ s, className = "" }: { s: SectorSummary; className?: string }) {
  const total = s.companies || 1;
  return (
    <div className={`flex h-2 w-full gap-[2px] overflow-hidden rounded-full ${className}`} role="img" aria-label={`${s.advancers} up, ${s.decliners} down, ${s.unchanged} flat`}>
      {s.advancers > 0 && <div className="h-full rounded-l-full bg-up" style={{ width: `${(s.advancers / total) * 100}%` }} />}
      {s.unchanged > 0 && <div className="h-full bg-subtle/60" style={{ width: `${(s.unchanged / total) * 100}%` }} />}
      {s.decliners > 0 && <div className="h-full rounded-r-full bg-down" style={{ width: `${(s.decliners / total) * 100}%` }} />}
    </div>
  );
}

function GrowwLink({ symbol, children }: { symbol: string; children: ReactNode }) {
  return (
    <a
      href={growwSearchUrl({ symbol })}
      target="_blank"
      rel="noopener noreferrer"
      title={`Open ${symbol} on Groww in a new tab. You place any order yourself.`}
      className="rounded font-semibold text-brand-strong hover:underline"
    >
      {children}
    </a>
  );
}

/** Wide screens: one row per company. */
export function CompanyTable({ companies }: { companies: MarketStock[] }) {
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="nm-table min-w-[820px]">
        <thead>
          <tr>
            <th>Company</th>
            <th className="text-right">Price (₹)</th>
            <th className="text-right">Today</th>
            <th className="text-right">1 week</th>
            <th className="text-right">1 month</th>
            <th className="text-right">3 months</th>
            <th>Trend</th>
            <th className="text-right">From 52w high</th>
            <th className="text-right">Traded</th>
            <th className="w-28">
              <span className="sr-only">Last 30 sessions</span>
            </th>
            <th>
              <span className="sr-only">Chart</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {companies.map((s) => (
            <tr key={s.symbol}>
              <td>
                <span className="block font-display font-semibold">{s.symbol}</span>
                <span className="block max-w-[14rem] truncate text-xs text-muted">{s.name}</span>
              </td>
              <td className="num text-right font-medium">{price(s.last)}</td>
              <td className="text-right">
                <ChangePill pct={s.change_pct} />
              </td>
              <td className="text-right">
                <Delta value={s.ret_1w} className="font-medium" />
              </td>
              <td className="text-right">
                <Delta value={s.ret_1m} className="font-medium" />
              </td>
              <td className="text-right">
                <Delta value={s.ret_3m} className="font-medium" />
              </td>
              <td>
                <Badge tone={TREND_TONE[s.trend]}>{s.trend}</Badge>
              </td>
              <td className="num text-right">{signedPct(s.from_high)}</td>
              <td className="num text-right whitespace-nowrap">₹{s.value_cr.toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr</td>
              <td>
                <Sparkline data={s.spark} height={28} />
              </td>
              <td className="whitespace-nowrap text-right text-xs">
                <GrowwLink symbol={s.symbol}>Chart ↗</GrowwLink>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Phones: one card per company. */
export function CompanyCards({ companies }: { companies: MarketStock[] }) {
  return (
    <ul className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:hidden">
      {companies.map((s) => (
        <li key={s.symbol} className="rounded-xl border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="font-display text-sm font-semibold">{s.symbol}</p>
              <p className="truncate text-[11px] text-muted">{s.name}</p>
            </div>
            <Badge tone={TREND_TONE[s.trend]}>{s.trend}</Badge>
          </div>
          <div className="mt-2 flex items-end justify-between gap-2">
            <p className="num text-lg font-semibold tracking-tight">₹{price(s.last)}</p>
            <ChangePill pct={s.change_pct} />
          </div>
          <div className="mt-2">
            <Sparkline data={s.spark} height={36} />
          </div>
          <div className="mt-2 grid grid-cols-3 gap-1 border-t border-border pt-2 text-[11px]">
            <p>
              <span className="block text-muted">1 week</span>
              <Delta value={s.ret_1w} digits={1} />
            </p>
            <p>
              <span className="block text-muted">1 month</span>
              <Delta value={s.ret_1m} digits={1} />
            </p>
            <p>
              <span className="block text-muted">3 months</span>
              <Delta value={s.ret_3m} digits={1} />
            </p>
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-muted">
            <span className="num">From 52w high {signedPct(s.from_high)}</span>
            <GrowwLink symbol={s.symbol}>Chart ↗</GrowwLink>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Small link chips to the other sector pages. */
export function SectorChips({ items, current }: { items: { key: string; label: string }[]; current?: string }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {items.map((o) => (
        <li key={o.key}>
          <Link
            href={`/sectors/${o.key}`}
            aria-current={o.key === current ? "page" : undefined}
            className={`inline-flex rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset ${
              o.key === current ? "bg-navy text-white ring-transparent" : "bg-surface text-muted ring-border hover:border-border-strong hover:text-text"
            }`}
          >
            {o.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}
