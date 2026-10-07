"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { growwSearchUrl } from "@/components/GrowwButton";
import { IconArrowRight } from "@/components/icons";
import { Sparkline } from "@/components/Sparkline";
import { Badge, Card, Eyebrow, LinkMore, Segmented, Skeleton } from "@/components/ui";
import { api, type MarketIndex, type MarketSnapshot, type MarketStock, type SnapList } from "@/lib/api";
import { fmtDate, signedPct } from "@/lib/format";

const num = (n: number, d = 2) => n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });

/** The market snapshot, refreshed every minute while the market is open (every 10 minutes otherwise). */
export function useMarket() {
  const [snap, setSnap] = useState<MarketSnapshot | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const load = () =>
      api.get<MarketSnapshot>("/market/snapshot").then(
        (d) => {
          if (stopped) return;
          setSnap(d);
          setFailed(false);
          timer = setTimeout(load, d.market_open ? 60_000 : 600_000);
        },
        () => {
          if (stopped) return;
          setFailed(true);
          timer = setTimeout(load, 120_000);
        },
      );
    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);
  return { snap, failed };
}

export function ChangePill({ pct, invert = false, size = "sm" }: { pct: number; invert?: boolean; size?: "sm" | "xs" }) {
  const good = invert ? pct < 0 : pct >= 0;
  return (
    <span
      className={`num inline-flex items-center gap-0.5 whitespace-nowrap rounded-md font-semibold ${size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-1 text-[11px]"} ${
        good ? "bg-up-soft text-up" : "bg-down-soft text-down"
      }`}
    >
      {pct >= 0 ? "▲" : "▼"} {Math.abs(pct * 100).toFixed(2)}%
    </span>
  );
}

export function liveNote(snap: MarketSnapshot) {
  return snap.live ? `Live · updated ${new Date(snap.updated_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}` : snap.as_of ? `Close of ${fmtDate(snap.as_of)}` : "";
}

// ---------------------------------------------------------------------------------------------- index cards
function IndexCard({ i }: { i: MarketIndex }) {
  const vix = i.symbol === "INDIAVIX";
  const good = vix ? i.change_pct < 0 : i.change_pct >= 0; // a rising VIX means more fear
  const body = (
    <>
      <div className={`absolute inset-x-0 top-0 h-[3px] ${good ? "bg-up" : "bg-down"} opacity-80`} />
      <p className="flex items-center justify-between gap-1 text-xs font-semibold text-muted" title={i.label}>
        <span className="truncate">{i.label}</span>
        {i.sector && <IconArrowRight width={13} height={13} className="shrink-0 text-subtle transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-brand" />}
      </p>
      <p className="num mt-1 text-lg font-semibold tracking-tight">{num(i.last)}</p>
      <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
        <ChangePill pct={i.change_pct} invert={vix} size="xs" />
        <span className={`num text-[11px] ${good ? "text-up" : "text-down"}`}>
          {i.change >= 0 ? "+" : "−"}
          {num(Math.abs(i.change))}
        </span>
      </div>
      <div className="mt-2">
        <Sparkline data={i.spark} height={34} up={vix ? i.spark[i.spark.length - 1] <= i.spark[0] : undefined} />
      </div>
      <p className="mt-1 flex justify-between text-[10px] text-muted">
        <span>3 months</span>
        <span className="num">{i.ret_3m === null ? "—" : signedPct(i.ret_3m)}</span>
      </p>
    </>
  );
  const cls = "lift group relative block overflow-hidden rounded-2xl border border-border bg-surface p-3.5 shadow-card";
  // a sector index opens the page with its companies
  return i.sector ? (
    <Link href={`/sectors/${i.sector}`} className={cls} title={`${i.label}: see its companies`}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function IndexWidgets({ snap }: { snap: MarketSnapshot | null }) {
  if (!snap)
    return (
      <div role="status" aria-label="Loading the indices" className="grid grid-cols-2 gap-3 sm:grid-cols-4 2xl:grid-cols-8">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="grid gap-2 rounded-2xl border border-border bg-surface p-3.5 shadow-card">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-9 w-full" />
          </div>
        ))}
      </div>
    );
  if (!snap.indices.length) return null;
  return (
    <section aria-label="NSE indices" className="grid grid-cols-2 gap-3 sm:grid-cols-4 2xl:grid-cols-8">
      {snap.indices.map((i) => (
        <IndexCard key={i.symbol} i={i} />
      ))}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------- breadth + sectors
function Gauge({ share, label }: { share: number; label: string }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const color = share >= 0.6 ? "var(--up)" : share >= 0.4 ? "var(--gold)" : "var(--down)";
  return (
    <div className="flex items-center gap-3">
      <svg width={64} height={64} className="-rotate-90 shrink-0" aria-hidden="true">
        <circle cx={32} cy={32} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={7} />
        <circle cx={32} cy={32} r={r} fill="none" stroke={color} strokeWidth={7} strokeLinecap="round" strokeDasharray={`${share * c} ${c}`} />
      </svg>
      <div>
        <p className="num text-xl font-semibold">{Math.round(share * 100)}%</p>
        <p className="text-xs leading-snug text-muted">{label}</p>
      </div>
    </div>
  );
}

type Period = "d" | "w" | "m";
const PERIOD_KEY: Record<Period, "change_pct" | "ret_1w" | "ret_1m"> = { d: "change_pct", w: "ret_1w", m: "ret_1m" };

function heat(pct: number, scale: number): string {
  const strength = Math.min(1, Math.abs(pct) / scale);
  const mix = Math.round(10 + strength * 40); // capped so the label on top stays easy to read
  return `color-mix(in oklab, var(${pct >= 0 ? "--up" : "--down"}) ${mix}%, var(--surface))`;
}

export function BreadthCard({ snap }: { snap: MarketSnapshot | null }) {
  const [period, setPeriod] = useState<Period>("d");
  if (!snap)
    return (
      <Card title="Market breadth">
        <div role="status" aria-label="Loading market breadth" className="grid gap-4">
          <Skeleton className="h-3 w-full rounded-full" />
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
          <Skeleton className="h-28" />
        </div>
      </Card>
    );
  const b = snap.breadth;
  if (!b.total) return null;
  const scale = period === "d" ? 0.02 : period === "w" ? 0.04 : 0.08;
  return (
    <Card title="Market breadth" subtitle={`${b.total} most-traded NSE stocks · ${liveNote(snap)}`}>
      <div>
        <div className="flex justify-between text-xs">
          <span className="font-semibold text-up">▲ {b.advancers} up</span>
          {b.unchanged > 0 && <span className="text-muted">{b.unchanged} flat</span>}
          <span className="font-semibold text-down">{b.decliners} down ▼</span>
        </div>
        <div className="mt-1.5 flex h-3 w-full gap-[2px] overflow-hidden rounded-full" role="img" aria-label={`${b.advancers} stocks up, ${b.decliners} down`}>
          <div className="h-full rounded-l-full bg-up" style={{ width: `${(b.advancers / b.total) * 100}%` }} />
          {b.unchanged > 0 && <div className="h-full bg-subtle/60" style={{ width: `${(b.unchanged / b.total) * 100}%` }} />}
          <div className="h-full rounded-r-full bg-down" style={{ width: `${(b.decliners / b.total) * 100}%` }} />
        </div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4">
        <Gauge share={b.above_50} label="above their 50-day average (short-term trend)" />
        <Gauge share={b.above_200} label="above their 200-day average (long-term trend)" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <p className="rounded-xl bg-up-soft px-3 py-2 ring-1 ring-inset ring-up/15">
          <b className="num text-sm text-up">{b.near_high}</b> <span className="text-muted">near a 52-week high</span>
        </p>
        <p className="rounded-xl bg-down-soft px-3 py-2 ring-1 ring-inset ring-down/15">
          <b className="num text-sm text-down">{b.near_low}</b> <span className="text-muted">near a 52-week low</span>
        </p>
      </div>
      {snap.sectors.length > 0 && (
        <div className="mt-5 border-t border-border pt-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-baseline gap-3">
              <Eyebrow>Sectors</Eyebrow>
              <LinkMore href="/sectors">All</LinkMore>
            </div>
            <Segmented
              label="Sector period"
              value={period}
              onChange={setPeriod}
              options={[
                { value: "d", label: "1D" },
                { value: "w", label: "1W" },
                { value: "m", label: "1M" },
              ]}
            />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-1.5">
            {snap.sectors.map((s) => {
              const v = s[PERIOD_KEY[period]];
              const inner = (
                <>
                  <p className="flex items-center justify-between gap-1 text-[11px] font-medium">
                    <span className="truncate">{s.label}</span>
                    {s.key && <IconArrowRight width={12} height={12} className="shrink-0 opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100" />}
                  </p>
                  <p className="num text-sm font-semibold">{v === null ? "—" : `${v >= 0 ? "▲" : "▼"} ${Math.abs(v * 100).toFixed(1)}%`}</p>
                </>
              );
              const style = { background: v === null ? "var(--surface-2)" : heat(v, scale) };
              const label = `${s.label}: ${signedPct(v, 2)}`;
              // each tile opens the page with that sector's companies
              return s.key ? (
                <Link key={s.symbol} href={`/sectors/${s.key}`} className="group block rounded-lg px-2.5 py-2 ring-1 ring-inset ring-transparent transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card hover:ring-border-strong" style={style} title={`${label}. See its companies`}>
                  {inner}
                </Link>
              ) : (
                <div key={s.symbol} className="rounded-lg px-2.5 py-2 transition-colors duration-300" style={style} title={label}>
                  {inner}
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] text-muted">Click a sector to see its companies.</p>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------------------------- stock snapshots
const TABS: { value: SnapList; label: string; explain: string }[] = [
  { value: "leaders", label: "Trend leaders", explain: "In an uptrend (above the 50- and 200-day averages) and within 10% of the 52-week high, ranked by 3-month gain." },
  { value: "gainers", label: "Top gainers", explain: "Biggest rises today." },
  { value: "losers", label: "Top losers", explain: "Biggest falls today." },
  { value: "active", label: "Most active", explain: "Most money traded in the last session." },
  { value: "highs", label: "52-week highs", explain: "Closest to (or at) their highest price of the past year." },
];

const TREND_TONE = { Uptrend: "good", Downtrend: "bad", Sideways: "neutral", New: "neutral" } as const;

function SnapCard({ s }: { s: MarketStock }) {
  return (
    <a
      href={growwSearchUrl({ symbol: s.symbol })}
      target="_blank"
      rel="noopener noreferrer"
      title={`${s.name} — open the chart on Groww`}
      className="lift group flex flex-col rounded-2xl border border-border bg-surface p-3.5 shadow-xs"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-display text-sm font-semibold tracking-tight group-hover:text-brand-strong">{s.symbol}</p>
          <p className="truncate text-[11px] text-muted">{s.name}</p>
        </div>
        <Badge tone={TREND_TONE[s.trend]}>{s.trend}</Badge>
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <p className="num text-lg font-semibold tracking-tight">₹{num(s.last)}</p>
        <ChangePill pct={s.change_pct} />
      </div>
      <div className="mt-2">
        <Sparkline data={s.spark} height={40} />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-1 border-t border-border pt-2 text-[11px]">
        <p>
          <span className="block text-muted">1 month</span>
          <span className={`num font-semibold ${(s.ret_1m ?? 0) >= 0 ? "text-up" : "text-down"}`}>{signedPct(s.ret_1m)}</span>
        </p>
        <p>
          <span className="block text-muted">From 52w high</span>
          <span className="num font-semibold">{signedPct(s.from_high)}</span>
        </p>
        <p>
          <span className="block text-muted">Traded</span>
          <span className="num font-semibold">₹{s.value_cr.toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr</span>
        </p>
      </div>
    </a>
  );
}

export function StockSnaps({ snap }: { snap: MarketSnapshot | null }) {
  const [tab, setTab] = useState<SnapList>("leaders");
  if (!snap)
    return (
      <Card title="Stock snapshots">
        <div role="status" aria-label="Loading stock snapshots" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-40 rounded-2xl" />
          ))}
        </div>
      </Card>
    );
  const list = snap.lists[tab].map((sym) => snap.stocks[sym]).filter(Boolean);
  const t = TABS.find((x) => x.value === tab)!;
  return (
    <Card title="Stock snapshots" subtitle={`The 200 most-traded NSE stocks · ${liveNote(snap)}`}>
      <Segmented label="Stock list" value={tab} onChange={setTab} options={TABS.map((x) => ({ value: x.value, label: x.label }))} />
      <p className="mt-3 text-xs text-muted">
        {t.explain} <b className="text-text">This shows what already happened. It is not a buy signal.</b> Click a card to open its chart on Groww.
      </p>
      {list.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-border-strong p-6 text-center text-sm text-muted">No stocks match right now.</p>
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {list.map((s) => (
            <SnapCard key={s.symbol} s={s} />
          ))}
        </div>
      )}
    </Card>
  );
}
