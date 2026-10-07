"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { growwSearchUrl } from "@/components/GrowwButton";
import { Badge, Skeleton } from "@/components/ui";
import type { DayMarket, DayStrip as Strip, IntradayPlan, IntradayRecap, PracticeTrade, SkippedDay } from "@/lib/api";
import { fmtDay, inr } from "@/lib/format";

const rupee = (n: number) => `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const money = (n: number) => `${n >= 0 ? "+" : "−"}${inr(Math.abs(n))}`;
const pct = (v: number) => `${v >= 0 ? "▲" : "▼"} ${Math.abs(v * 100).toFixed(2)}%`;
const rr = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}R`;
const tone = (v: number) => (v >= 0 ? "text-up" : "text-down");
const EXIT = { stop: "stop-loss hit", target: "target hit", time: "sold at 3:00 PM" } as const;

function skippedNote(days: SkippedDay[]): string | null {
  if (!days.length) return null;
  const parts = days.map((d) => `${fmtDay(d.date)} (${d.reason === "Weekend" ? "weekend" : d.reason})`);
  return `Skipped: ${parts.join(", ")}`;
}

function Shell({ label, date, accent, chip, note, children }: { label: string; date: string; accent: string; chip?: ReactNode; note?: string | null; children: ReactNode }) {
  return (
    <section className="relative flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-surface p-5 shadow-card">
      <span className="absolute inset-x-0 top-0 h-1" style={{ background: accent }} />
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">{label}</p>
          <h2 className="mt-0.5 text-xl font-semibold">{fmtDay(date)}</h2>
        </div>
        {chip}
      </header>
      {note && <p className="mt-1 text-xs leading-relaxed text-muted">{note}</p>}
      <div className="mt-4 flex min-w-0 flex-1 flex-col gap-4 text-sm">{children}</div>
    </section>
  );
}

function Heading({ children }: { children: ReactNode }) {
  return <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">{children}</p>;
}

function MarketRecap({ m }: { m: DayMarket }) {
  const total = m.advancers + m.decliners || 1;
  return (
    <div className="grid grid-cols-1 gap-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-surface-2 px-3 py-2 ring-1 ring-inset ring-border">
          <p className="text-xs text-muted">Nifty 50</p>
          <p className="num text-base font-semibold">{m.nifty.close.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</p>
          <p className={`num text-xs font-semibold ${tone(m.nifty.change_pct)}`}>{pct(m.nifty.change_pct)}</p>
        </div>
        <div className="rounded-xl bg-surface-2 px-3 py-2 ring-1 ring-inset ring-border">
          <p className="text-xs text-muted">Sensex</p>
          <p className="num text-base font-semibold">{m.sensex ? m.sensex.close.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—"}</p>
          {m.sensex && <p className={`num text-xs font-semibold ${tone(m.sensex.change_pct)}`}>{pct(m.sensex.change_pct)}</p>}
        </div>
      </div>
      <div>
        <div className="flex justify-between text-xs">
          <span className="font-semibold text-up">▲ {m.advancers} rose</span>
          <span className="font-semibold text-down">{m.decliners} fell ▼</span>
        </div>
        <div className="mt-1 flex h-2 gap-[2px] overflow-hidden rounded-full" role="img" aria-label={`${m.advancers} stocks rose, ${m.decliners} fell`}>
          <div className="h-full rounded-l-full bg-up" style={{ width: `${(m.advancers / total) * 100}%` }} />
          <div className="h-full rounded-r-full bg-down" style={{ width: `${(m.decliners / total) * 100}%` }} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 text-xs">
        {(["gainers", "losers"] as const).map((k) => (
          <ul key={k} className="grid min-w-0 grid-cols-1 gap-1">
            <li className="text-muted">{k === "gainers" ? "Biggest rises" : "Biggest falls"}</li>
            {m[k].map((x) => (
              <li key={x.symbol} className="flex min-w-0 justify-between gap-2">
                <span className="truncate font-medium">{x.symbol}</span>
                <span className={`num shrink-0 font-semibold ${tone(x.change_pct)}`}>{pct(x.change_pct)}</span>
              </li>
            ))}
          </ul>
        ))}
      </div>
    </div>
  );
}

function TradeLine({ t }: { t: PracticeTrade }) {
  return (
    <li className="flex min-w-0 items-baseline justify-between gap-2">
      <span className="min-w-0 truncate">
        <b className="font-semibold">{t.symbol}</b> <span className="text-muted">bought {t.entry_time}, {EXIT[t.exit_reason]}</span>
      </span>
      <span className={`num shrink-0 font-semibold ${tone(t.net_pnl)}`}>{money(t.net_pnl)}</span>
    </li>
  );
}

function Scoreboard({ r }: { r: IntradayRecap }) {
  const total = r.first_trades.reduce((s, t) => s + t.net_pnl, 0);
  const signals = r.setups.reduce((s, x) => s + x.signals, 0);
  return (
    <div className="grid grid-cols-1 gap-2">
      <Heading>Same-day setups · practice scoreboard</Heading>
      <p className="text-xs leading-relaxed text-muted">
        {r.filter_ok
          ? "The market filter was on, so the rules allowed practice trades."
          : "The rules stood aside this day (the Nifty was below its 50-day average)."}{" "}
        {signals === 0
          ? "No setup gave a signal anyway."
          : r.filter_ok
            ? `The first ${r.first_trades.length} signal${r.first_trades.length === 1 ? "" : "s"}, with ${inr(r.capital)} of pretend money:`
            : `Had you traded the first ${r.first_trades.length} signal${r.first_trades.length === 1 ? "" : "s"} anyway, with ${inr(r.capital)}:`}
      </p>
      {r.first_trades.length > 0 && (
        <ul className="grid grid-cols-1 gap-1 rounded-xl bg-surface-2 px-3 py-2 text-xs ring-1 ring-inset ring-border">
          {r.first_trades.map((t) => (
            <TradeLine key={`${t.symbol}-${t.setup}`} t={t} />
          ))}
          <li className="mt-1 flex justify-between border-t border-border pt-1 font-semibold">
            <span>Result for the day</span>
            <span className={`num ${tone(total)}`}>{money(total)}</span>
          </li>
        </ul>
      )}
      <table className="w-full text-xs">
        <thead className="text-muted">
          <tr>
            <th className="py-1 text-left font-normal">Setup</th>
            <th className="py-1 pl-2 text-right font-normal">Signals</th>
            <th className="py-1 pl-2 text-right font-normal">Won</th>
            <th className="py-1 pl-2 text-right font-normal">Average</th>
          </tr>
        </thead>
        <tbody>
          {r.setups.map((s) => (
            <tr key={s.key} className="border-t border-border">
              <td className="py-1 pr-2">{s.label}</td>
              <td className="num py-1 pl-2 text-right">{s.signals}</td>
              <td className="num py-1 pl-2 text-right">{s.signals ? s.won : "—"}</td>
              <td className={`num py-1 pl-2 text-right font-semibold ${s.avg_r === null ? "text-muted" : tone(s.avg_r)}`}>{s.avg_r === null ? "—" : rr(s.avg_r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {r.watchlist.length > 0 && (
        <div className="text-xs">
          <p className="text-muted">The stocks on that day&apos;s watchlist:</p>
          <ul className="mt-1 grid grid-cols-1 gap-0.5">
            {r.watchlist.map((w) => (
              <li key={w.symbol} className="flex justify-between gap-2">
                <span className="font-medium">{w.symbol}</span>
                {w.outcome ? (
                  <span className={`num font-semibold ${tone(w.outcome.net_pnl)}`}>
                    {EXIT[w.outcome.exit_reason]} · {money(w.outcome.net_pnl)}
                  </span>
                ) : (
                  <span className="text-muted">never crossed ₹{w.trigger.toLocaleString("en-IN")}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function PlanView({ plan }: { plan: IntradayPlan }) {
  const aside = plan.verdict === "stand_aside";
  return (
    <div className="grid grid-cols-1 gap-4">
      <div className={`rounded-xl px-3.5 py-3 ring-1 ${aside ? "bg-warn-soft ring-warn/25" : "bg-good-soft ring-good/25"}`}>
        <p className="font-semibold">{aside ? "Stand aside: watch, don't trade" : `Practice trades allowed: up to ${plan.max_trades}, pretend money only`}</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          The Nifty 50 closed at <span className="num">{plan.filter.nifty.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>,{" "}
          {plan.filter.ok ? "above" : "below"} its {plan.filter.days}-day average (
          <span className="num">{plan.filter.average.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>).{" "}
          {aside ? "These setups only buy in a rising market, so the rules take no trade." : `Sell everything by ${plan.exit_time}.`}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-2">
        <Heading>
          {aside ? "Stocks to watch (not to buy)" : "Practice watchlist"} · {plan.watch_setup}
        </Heading>
        {plan.watchlist.length === 0 ? (
          <p className="text-xs text-muted">No stock closed strongly enough to be worth watching.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-1.5">
            {plan.watchlist.map((w) => (
              <li key={w.symbol} className="rounded-xl border border-border bg-surface px-3 py-2.5 text-xs shadow-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate">
                    <b className="text-sm font-semibold">{w.symbol}</b> <span className="text-muted">closed {rupee(w.prev_close)}</span>
                  </span>
                  <a href={growwSearchUrl({ symbol: w.symbol })} target="_blank" rel="noopener noreferrer" className="shrink-0 rounded font-semibold text-brand-strong hover:underline">
                    Chart ↗
                  </a>
                </div>
                <div className="num mt-1 grid grid-cols-3 gap-2">
                  <span>
                    <span className="block text-muted">Buy only above</span>
                    <b className="font-semibold">{rupee(w.trigger)}</b>
                  </span>
                  <span>
                    <span className="block text-muted">Stop-loss</span>
                    <b className="font-semibold text-down">{rupee(w.stop)}</b>
                  </span>
                  <span>
                    <span className="block text-muted">Target</span>
                    <b className="font-semibold text-up">{rupee(w.target)}</b>
                  </span>
                </div>
                <p className="num mt-1 text-muted">
                  {w.qty} shares ≈ {inr(w.amount)} · risk {inr(w.risk)} · charges about {inr(w.charges)}
                </p>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[11px] leading-relaxed text-muted">
          Valid after 9:30 AM and before 1:00 PM. If the stock opens above the buy level, skip it. Levels are from the last close and the rule in
          the list below. In testing this setup lost money, so use it to learn, with pretend money.
        </p>
      </div>

      <details className="group/d rounded-xl border border-border bg-surface-2/50 px-3.5 py-2.5 text-xs open:bg-surface">
        <summary className="flex list-none items-center justify-between gap-2 rounded text-sm font-medium hover:text-brand-strong">
          The three setups and how they tested <span className="text-muted transition-transform duration-200 group-open/d:rotate-180">⌄</span>
        </summary>
        <ul className="mt-2 grid grid-cols-1 gap-2.5">
          {plan.setups.map((s) => (
            <li key={s.key}>
              <p className="flex flex-wrap items-center gap-1.5">
                <b className="font-semibold">{s.label}</b>
                {s.allowed ? <Badge tone="good">passed</Badge> : <Badge tone="bad">lost money in tests</Badge>}
                <span className="text-muted">{s.when}</span>
              </p>
              <p className="mt-0.5 leading-relaxed text-muted">{s.plain}</p>
              {s.tested && (
                <p className="num mt-0.5">
                  Since 2024: {s.tested.trades.toLocaleString("en-IN")} trades, {Math.round(s.tested.win_rate * 100)}% won,{" "}
                  <b className={tone(s.tested.avg_r)}>{rr(s.tested.avg_r)}</b> a trade after charges ({rr(s.tested.avg_r_before_charges)} before).
                </p>
              )}
            </li>
          ))}
        </ul>
      </details>

      <details className="group/d rounded-xl border border-border bg-surface-2/50 px-3.5 py-2.5 text-xs open:bg-surface">
        <summary className="flex list-none items-center justify-between gap-2 rounded text-sm font-medium hover:text-brand-strong">
          {plan.rules.length} rules for a beginner <span className="text-muted transition-transform duration-200 group-open/d:rotate-180">⌄</span>
        </summary>
        <ol className="mt-2 grid list-decimal gap-1.5 pl-4 leading-relaxed text-muted">
          {plan.rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ol>
      </details>
    </div>
  );
}

/** Yesterday · Today · Tomorrow, as trading days: weekends and exchange holidays are skipped and named. */
export function DayStrip({ days }: { days: Strip | undefined | null }) {
  if (!days)
    return (
      <div role="status" aria-label="Loading yesterday, today and tomorrow" className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="grid gap-3 rounded-2xl border border-border bg-surface p-5 shadow-card">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-6 w-36" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-3.5 w-4/5" />
            <Skeleton className="h-3.5 w-3/5" />
          </div>
        ))}
      </div>
    );
  const { previous, today, next } = days;
  const state = today.market.state;
  const closedToday = today.status !== "trading";
  return (
    <div className="grid grid-cols-1 gap-3">
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-3">
        <Shell
          label={previous.is_yesterday ? "Yesterday" : "Yesterday · last trading day"}
          date={previous.date}
          accent="var(--subtle)"
          note={skippedNote(previous.skipped)}
          chip={previous.market ? <Badge tone={previous.market.nifty.change_pct >= 0 ? "good" : "bad"}>Nifty {pct(previous.market.nifty.change_pct)}</Badge> : undefined}
        >
          {previous.market ? <MarketRecap m={previous.market} /> : <p className="text-muted">Prices for this day aren&apos;t in yet. Press Refresh (top right).</p>}
          {previous.recap ? <Scoreboard r={previous.recap} /> : previous.market && <p className="text-xs text-muted">The practice scoreboard for this day isn&apos;t ready. Press Refresh.</p>}
        </Shell>

        <Shell
          label="Today"
          date={today.date}
          accent="var(--brand)"
          chip={
            closedToday ? (
              <Badge tone={today.status === "special" ? "gold" : "neutral"}>{today.status === "weekend" ? "Weekend" : today.status === "special" ? "Special session" : "Holiday"}</Badge>
            ) : state === "open" ? (
              <Badge tone="good">Market open</Badge>
            ) : state === "pre" ? (
              <Badge tone="warn">Opens 9:15 AM</Badge>
            ) : (
              <Badge tone="neutral">Closed for the day</Badge>
            )
          }
        >
          {closedToday ? (
            <>
              <div className="rounded-xl bg-surface-2 px-3.5 py-3 ring-1 ring-inset ring-border">
                <p className="font-semibold">{today.status === "special" ? today.name : `Market closed${today.name ? ` · ${today.name}` : ""}`}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted">
                  {today.note ?? "No trading today."} The next session is <b className="text-text">{fmtDay(today.market.next_open)}</b>.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-1.5 text-xs leading-relaxed text-muted">
                <Heading>A good use of today</Heading>
                <p>1. Read the beginner rules in the next card. They matter more than any stock pick.</p>
                <p>2. Look at how the last session&apos;s signals turned out (left): that is what trading them would have felt like.</p>
                <p>
                  3. Your long-term money doesn&apos;t wait for market hours: see <Link href="/plan" className="font-semibold text-brand-strong hover:underline">My plan</Link>.
                </p>
              </div>
            </>
          ) : (
            <>
              {today.result && <MarketRecap m={today.result} />}
              {today.recap && <Scoreboard r={today.recap} />}
              {!today.result &&
                (today.plan ? <PlanView plan={today.plan} /> : <p className="text-muted">Today&apos;s practice plan isn&apos;t ready. Press Refresh (top right).</p>)}
              {state === "closed" && !today.result && <p className="text-xs text-muted">The market has closed. Today&apos;s results appear after about 4:45 PM, or press Refresh.</p>}
            </>
          )}
        </Shell>

        <Shell
          label={next.is_tomorrow ? "Tomorrow" : "Tomorrow · next trading day"}
          date={next.date}
          accent="var(--series-1)"
          note={skippedNote(next.skipped)}
          chip={next.plan ? <Badge tone={next.plan.verdict === "practice" ? "good" : "warn"}>{next.plan.verdict === "practice" ? "Practice day" : "Stand aside"}</Badge> : undefined}
        >
          {next.plan ? (
            <PlanView plan={next.plan} />
          ) : next.waiting_for_close ? (
            <p className="text-muted">The plan for {fmtDay(next.date)} is written after today&apos;s close, at about 4:45 PM.</p>
          ) : (
            <p className="text-muted">The plan isn&apos;t ready yet. Press Refresh (top right).</p>
          )}
        </Shell>
      </div>
      <p className="text-xs leading-relaxed text-muted">
        Same-day trading here is practice with pretend money. None of the three setups made money after charges in testing, so nothing in this row is
        a recommendation to buy.
      </p>
    </div>
  );
}
