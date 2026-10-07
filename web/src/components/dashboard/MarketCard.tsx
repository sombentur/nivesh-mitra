"use client";

import { LineChart, type ChartRange } from "@/components/LineChart";
import { Badge, Card, Stat } from "@/components/ui";
import type { MarketMood } from "@/lib/api";
import { fmtDate, signedPct } from "@/lib/format";

const MOOD_TEXT = {
  Positive: "Uptrend. Conditions are friendlier for buying, though any single stock can still fall.",
  Mixed: "No clear direction. Be choosy and keep positions small.",
  Weak: "Downtrend. Most stocks fall with the market; protecting capital matters more than finding trades.",
};

const RANGES: ChartRange[] = [
  { key: "1m", label: "1M", days: 31 },
  { key: "3m", label: "3M", days: 92 },
  { key: "6m", label: "6M", days: 0 },
];

export function MarketCard({ market }: { market: MarketMood | null }) {
  if (!market)
    return (
      <Card title="Market today">
        <p className="text-sm text-muted">Index prices appear after the first Groww price download.</p>
      </Card>
    );
  const up = market.change_pct >= 0;
  return (
    <Card
      className="h-full"
      title={
        <span className="flex items-center gap-2">
          Nifty 50 <Badge tone={market.tone}>Market mood: {market.mood}</Badge>
        </span>
      }
      subtitle={`Daily closes · up to ${fmtDate(market.as_of)}`}
    >
      <div className="flex flex-wrap items-end gap-x-5 gap-y-2">
        <p className="num text-4xl font-semibold tracking-tight">{market.nifty.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</p>
        <p className={`num mb-1 rounded-lg px-2 py-0.5 text-sm font-semibold ${up ? "bg-up-soft text-up" : "bg-down-soft text-down"}`}>
          {up ? "▲" : "▼"} {signedPct(market.change_pct, 2)} <span className="font-normal text-muted">on the day</span>
        </p>
      </div>
      <div className="mt-4">
        <LineChart
          data={market.chart}
          valueLabel="Nifty 50"
          format={(v) => v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
          height={230}
          ranges={RANGES}
          defaultRange="6m"
        />
      </div>
      <div className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-[1fr_auto]">
        <p className="text-sm leading-relaxed">
          <b>{MOOD_TEXT[market.mood]}</b> <span className="text-muted">{market.reason}</span>
        </p>
        {market.vix !== null && (
          <Stat label="India VIX (fear gauge)" value={market.vix.toFixed(1)} hint={market.vix < 15 ? "calm" : market.vix > 20 ? "nervous" : "normal"} />
        )}
      </div>
    </Card>
  );
}
