"use client";

import Link from "next/link";
import { GrowwButton } from "@/components/GrowwButton";
import { IconArrowRight, IconClock, IconPause } from "@/components/icons";
import { Badge, buttonClass, Card, Eyebrow, LinkMore, SkeletonLines, Stat } from "@/components/ui";
import type { DataStatus, IntradaySetupView, SetupBacktestView, TradingIdea, TradingOverview } from "@/lib/api";
import { fmtDate, fmtDay, inr, pctReturn, signedPct } from "@/lib/format";

const rupee = (n: number) => `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

function IdeaRow({ idea, rank }: { idea: TradingIdea; rank: number }) {
  const stopPct = idea.stop / idea.entry_high - 1;
  const targetPct = idea.target / idea.entry_high - 1;
  return (
    <li className="lift rounded-2xl border border-border bg-surface p-4 shadow-xs">
      <div className="flex flex-wrap items-start gap-3">
        <span className="num grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-navy text-sm font-semibold text-white">{rank}</span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-display text-base font-semibold tracking-tight">{idea.symbol}</span>
            <Badge tone="brand">{idea.setup_label}</Badge>
            <Badge tone={idea.confidence === "high" ? "good" : idea.confidence === "medium" ? "neutral" : "warn"}>{idea.confidence} confidence</Badge>
          </p>
          <p className="truncate text-xs text-muted">{idea.name}</p>
        </div>
        <div className="flex gap-2">
          <GrowwButton symbol={idea.symbol} label="Chart on Groww" variant="secondary" />
          <Link href="/trading" className={`${buttonClass("primary", "sm")} gap-1`}>
            Practice buy <IconArrowRight width={14} height={14} />
          </Link>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Buy between" value={`${rupee(idea.entry_low)} – ${rupee(idea.entry_high)}`} hint="limit order; skip if it opens higher" />
        <Stat label="Stop-loss" value={rupee(idea.stop)} hint={`${signedPct(stopPct)} · sell if it falls here`} tone="bad" />
        <Stat label="Target" value={rupee(idea.target)} hint={`${signedPct(targetPct)} · within ${idea.hold_days} days`} tone="good" />
        <Stat label="Quantity" value={`${idea.qty} shares`} hint={`≈ ${inr(idea.amount)} · risk ${inr(idea.risk_amount)}`} />
      </div>
      <p className="mt-3 text-xs text-muted">
        In past tests this setup won {pctReturn(idea.backtest.win_rate, 0)} of {idea.backtest.trades.toLocaleString("en-IN")} trades, after all charges. Reward is{" "}
        {idea.reward_risk.toFixed(1)}× the risk.
      </p>
    </li>
  );
}

function PipelineStep({ state, children }: { state: "done" | "running" | "todo"; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2.5">
      <span
        className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-bold ${
          state === "done" ? "bg-brand text-on-brand" : state === "running" ? "bg-warn-soft text-warn ring-1 ring-warn/40" : "bg-surface-2 text-muted ring-1 ring-border"
        }`}
      >
        {state === "done" ? "✓" : state === "running" ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-warn" /> : ""}
      </span>
      <span className={state === "todo" ? "text-muted" : ""}>{children}</span>
    </li>
  );
}

/** "Which share do I buy tomorrow?" — the top practice ideas for the next session, or a clear "no trade". */
const r2 = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}R`;

function SetupResults({ setups, intraday }: { setups: SetupBacktestView[]; intraday: IntradaySetupView[] }) {
  const tested = setups.filter((b) => b.tested && b.stats);
  const same = intraday.filter((b) => b.tested && b.test);
  if (!tested.length && !same.length) return null;
  return (
    <div className="border-t border-border pt-4">
      <Eyebrow>What the strategies did in 6 years of past prices</Eyebrow>
      <ul className="mt-3 grid gap-2">
        {tested.map((b) => (
          <li key={b.setup} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface px-3 py-2.5 text-sm ring-1 ring-border">
            <span className="flex items-center gap-2">
              {b.allowed ? <Badge tone="good">ON</Badge> : <Badge tone="bad">OFF</Badge>}
              <span className="font-medium">{b.label}</span>
            </span>
            <span className="num text-xs text-muted">
              {b.stats!.trades.toLocaleString("en-IN")} trades{b.stats!.avg_r !== undefined ? ` · ${r2(b.stats!.avg_r)} after charges` : ""}
              {b.stats!.avg_r_before_charges !== undefined ? ` · ${r2(b.stats!.avg_r_before_charges)} before` : ""}
            </span>
          </li>
        ))}
        {same.map((b) => (
          <li key={b.setup} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface px-3 py-2.5 text-sm ring-1 ring-border">
            <span className="flex items-center gap-2">
              {b.allowed ? <Badge tone="good">ON</Badge> : <Badge tone="bad">OFF</Badge>}
              <span className="font-medium">{b.label}</span>
              <Badge tone="gold">Same day</Badge>
            </span>
            <span className="num text-xs text-muted">
              {b.test!.trades.toLocaleString("en-IN")} trades since 2024
              {b.test!.avg_r !== undefined ? ` · ${r2(b.test!.avg_r)} after charges` : ""}
              {b.test!.avg_r_before_charges !== undefined ? ` · ${r2(b.test!.avg_r_before_charges)} before` : ""}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] leading-relaxed text-muted">
        R = the amount risked on one trade. A strategy is switched on only if it made money after all charges. Same-day strategies are judged only
        on 2024 onwards, data they were never tuned on.
      </p>
    </div>
  );
}

export function StockIdeas({
  ideas,
  overview,
  status,
  setups = [],
  intraday = [],
}: {
  ideas: TradingIdea[] | null;
  overview: TradingOverview | null;
  status: DataStatus | null;
  setups?: SetupBacktestView[];
  intraday?: IntradaySetupView[];
}) {
  const session = overview?.ideas_status?.for_session ?? ideas?.[0]?.for_session ?? null;
  const blocked = overview?.state.cooling_off_reason || overview?.state.loss_limit_reason;
  const job = (name: string) => status?.jobs.find((j) => j.name === name);
  const backfill = job("stock_backfill");
  const backtests = job("stock_backtests");
  const tested = !!backtests?.last_success;
  const capital = overview?.state.account_start_capital;

  return (
    <Card
      className="h-full"
      title={session ? `Stocks to buy · ${fmtDay(session)}` : "Stocks to buy next session"}
      subtitle={
        <>
          Short-term (swing) ideas for practice with {capital ? inr(capital) : "pretend money"}.
          {overview?.practice.ends_on && ` Real money unlocks after ${fmtDate(overview.practice.ends_on)} if your practice results are good.`}
        </>
      }
      action={<LinkMore href="/trading">Trading</LinkMore>}
    >
      {ideas === null ? (
        <SkeletonLines lines={5} label="Loading stock ideas" />
      ) : ideas.length > 0 ? (
        <ol className="grid grid-cols-1 gap-3">
          {ideas.slice(0, 3).map((idea, i) => (
            <IdeaRow key={idea.id} idea={idea} rank={i + 1} />
          ))}
        </ol>
      ) : (
        <div className="flex h-full flex-col justify-between gap-4 rounded-2xl border border-dashed border-border-strong bg-surface-2/50 p-5">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-navy text-ink-accent">
              <IconPause />
            </span>
            <div>
              <p className="font-display text-lg font-semibold">{blocked ? "Trading paused" : "No trade today"}</p>
              <p className="mt-1 text-sm leading-relaxed text-muted">
                {blocked ||
                  overview?.ideas_status?.reason ||
                  "No stock passed every rule for the next session."}{" "}
                Not buying is a valid decision: protecting your money comes first.
              </p>
            </div>
          </div>
          {tested && <SetupResults setups={setups} intraday={intraday} />}
          {!tested && (
            <div className="border-t border-border pt-4">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                <IconClock width={14} height={14} /> One-time setup, runs by itself
              </p>
              <ol className="mt-3 grid gap-2 text-sm">
                <PipelineStep state={(overview?.data.universe_size ?? 0) > 0 ? "done" : "running"}>
                  Pick the {overview?.data.universe_size || 200} most-traded NSE stocks
                </PipelineStep>
                <PipelineStep state={backfill?.running ? "running" : backfill?.last_success && (overview?.data.universe_size ?? 0) > 0 ? "done" : "todo"}>
                  Download their prices since 2020
                  {backfill?.running && backfill.progress ? ` · ${backfill.progress.done} of ${backfill.progress.total}` : ""}
                </PipelineStep>
                <PipelineStep state={backtests?.running ? "running" : "todo"}>Test each strategy on 6 years of history, after all charges</PipelineStep>
                <PipelineStep state="todo">Ideas appear here each trading day after 4:45 PM, for the next morning</PipelineStep>
              </ol>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
