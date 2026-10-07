"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { confirmDialog } from "@/components/ConfirmDialog";
import { GrowwCheck } from "@/components/GrowwCheck";
import { IconPause } from "@/components/icons";
import { Badge, Button, Card, inputClass, Notice, PageHeader, PageSkeleton, Spinner, StatTile } from "@/components/ui";
import { api, type IntradaySetupView, type PaperSummary, type PaperTradeView, type SetupBacktestView, type TradingIdea, type TradingOverview } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";

const rupee = (n: number | null | undefined, digits = 2) =>
  n === null || n === undefined ? "—" : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
const signedRupee = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `${n >= 0 ? "+" : "−"}${inr(Math.abs(n))}`);
const pct0 = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(0)}%`);
const rFmt = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`);

function Stat({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: "good" | "bad" | "warn" }) {
  return <StatTile label={label} value={<span className="text-lg">{value}</span>} hint={note} tone={tone} />;
}

/** Green for a gain, red for a loss, nothing for zero or unknown. */
const sign = (v: number | null | undefined) => (v === null || v === undefined || v === 0 ? undefined : v > 0 ? "good" : "bad");

function IdeaCard({ idea, onBought }: { idea: TradingIdea; onBought: () => void }) {
  const [qty, setQty] = useState(idea.qty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const taken = idea.status === "taken";

  async function paperBuy() {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/trading/ideas/${idea.id}/paper-buy`, { qty });
      onBought();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't place the practice trade");
    } finally {
      setBusy(false);
    }
  }

  const bt = idea.backtest;
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-display text-xl font-semibold tracking-tight">
            {idea.symbol} <span className="font-sans text-sm font-normal tracking-normal text-muted">{idea.name}</span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm">
            <Badge tone="brand">{idea.setup_label}</Badge>
            <Badge tone={idea.confidence === "high" ? "good" : idea.confidence === "medium" ? "warn" : "bad"}>{idea.confidence} confidence</Badge>
            <span className="text-muted">for {fmtDate(idea.for_session)}</span>
          </div>
        </div>
        {taken && <Badge tone="good">✓ Practice trade placed</Badge>}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Buy between" value={`${rupee(idea.entry_low)} – ${rupee(idea.entry_high)}`} note={`closed at ${rupee(idea.close)}`} />
        <Stat label="Stop-loss (sell if it falls to)" value={rupee(idea.stop)} note={`max loss ${inr(idea.risk_amount)} + charges`} tone="bad" />
        <Stat label="Target (sell if it rises to)" value={rupee(idea.target)} note={`gain ${inr(idea.reward_amount)} before charges`} tone="good" />
        <Stat label="Reward : risk" value={`${idea.reward_risk.toFixed(1)} : 1`} note={`hold up to ${idea.hold_days} trading days`} />
        <Stat label="Quantity" value={idea.qty} note={`${inr(idea.amount)} of your capital`} />
        <Stat label="Charges (buy + sell)" value={inr(idea.charges)} note={`price must rise ${(idea.breakeven_pct * 100).toFixed(1)}% to break even`} />
        <Stat label="Past win rate" value={pct0(bt.win_rate)} note={`${bt.trades} past trades, after costs`} />
        <Stat label="Average result" value={rFmt(bt.avg_r)} note="per trade, after costs" tone={sign(bt.avg_r)} />
      </div>

      <div className="mt-5 grid gap-5 text-sm leading-relaxed md:grid-cols-2">
        <div>
          <p className="font-display text-[15px] font-semibold">Why this idea</p>
          <p className="mt-1 text-muted">{idea.setup_plain}</p>
          <ul className="mt-2 grid gap-1.5">
            {idea.reasons.map((r) => (
              <li key={r} className="flex gap-2">
                <span className="font-semibold text-brand" aria-hidden="true">✓</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-display text-[15px] font-semibold">Why not? (the risks)</p>
          <ul className="mt-2 grid gap-1.5 text-muted">
            {idea.risks.map((r) => (
              <li key={r} className="flex gap-2">
                <span className="font-semibold text-warn" aria-hidden="true">!</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <details className="group/d mt-5 rounded-xl border border-border bg-surface-2/50 px-3.5 py-2.5 text-sm open:bg-surface">
        <summary className="flex list-none items-center justify-between gap-2 rounded font-medium hover:text-brand-strong">
          What would I do on Groww? (for later — practice only for now) <span className="text-muted transition-transform duration-200 group-open/d:rotate-180">⌄</span>
        </summary>
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 leading-relaxed text-muted">
          {idea.groww_steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </details>

      {!taken && (
        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-border pt-4">
          <label className="flex items-center gap-2 text-sm font-medium">
            Quantity
            <input
              type="number"
              min={1}
              max={idea.qty}
              className={`${inputClass} w-24 font-normal`}
              value={qty}
              onChange={(e) => setQty(Math.max(1, Math.min(idea.qty, Number(e.target.value) || 1)))}
            />
          </label>
          <Button onClick={paperBuy} disabled={busy}>
            {busy && <Spinner />}
            {busy ? "Placing…" : "Paper-buy (practice)"}
          </Button>
          <span className="text-xs text-muted">Fills at the next session&apos;s opening price if it opens inside the buy range.</span>
        </div>
      )}
      {error && (
        <div className="mt-3">
          <Notice tone="bad">{error}</Notice>
        </div>
      )}
    </Card>
  );
}

function TradesTable({ trades, onAction }: { trades: PaperTradeView[]; onAction: () => void }) {
  async function act(t: PaperTradeView, what: "cancel" | "close") {
    if (what === "close") {
      const ok = await confirmDialog({
        title: `Sell ${t.symbol} now?`,
        body: "The practice trade is closed at the last closing price, and charges are taken off as they would be with real money.",
        confirmLabel: "Sell now",
      });
      if (!ok) return;
    }
    await api.post(`/trading/paper/${t.id}/${what}`);
    onAction();
  }
  if (!trades.length) return <p className="rounded-xl border border-dashed border-border-strong px-4 py-5 text-center text-sm text-muted">No practice trades yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="nm-table min-w-[720px]">
        <thead>
          <tr>
            <th>Stock</th>
            <th>Status</th>
            <th className="text-right">Qty</th>
            <th className="text-right">Bought</th>
            <th className="text-right">Stop / target</th>
            <th className="text-right">Sold</th>
            <th className="text-right">Result (after charges)</th>
            <th>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td className="font-display font-semibold">{t.symbol}</td>
              <td>
                <Badge tone={t.status === "closed" ? ((t.net_pnl ?? 0) > 0 ? "good" : "bad") : t.status === "open" ? "info" : "neutral"}>
                  {t.status === "closed" ? t.exit_reason : t.status === "pending" ? `buys ${fmtDate(t.for_session)}` : t.status}
                </Badge>
              </td>
              <td className="num text-right">{t.qty}</td>
              <td className="num text-right">
                {t.entry_price ? rupee(t.entry_price) : "—"}
                {t.entry_date && <div className="mt-0.5 text-xs text-muted">{fmtDate(t.entry_date)}</div>}
              </td>
              <td className="num text-right text-muted">
                {rupee(t.stop)} / {rupee(t.target)}
              </td>
              <td className="num text-right">
                {t.exit_price ? rupee(t.exit_price) : "—"}
                {t.exit_date && <div className="mt-0.5 text-xs text-muted">{fmtDate(t.exit_date)}</div>}
              </td>
              <td className="num text-right">
                {t.net_pnl !== null ? (
                  <>
                    <span className={`font-semibold ${t.net_pnl > 0 ? "text-up" : "text-down"}`}>
                      {t.net_pnl > 0 ? "▲" : "▼"} {signedRupee(t.net_pnl)}
                    </span>
                    <div className="mt-0.5 text-xs text-muted">
                      {rFmt(t.r_multiple)} · charges {inr(t.charges ?? 0)}
                    </div>
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td className="text-right">
                {t.status === "pending" && (
                  <button className="rounded-lg px-2 py-1 text-xs font-medium text-muted hover:bg-bad-soft hover:text-bad" onClick={() => act(t, "cancel")}>
                    Cancel
                  </button>
                )}
                {t.status === "open" && (
                  <button className="rounded-lg px-2 py-1 text-xs font-medium text-muted hover:bg-bad-soft hover:text-bad" onClick={() => act(t, "close")}>
                    Sell now
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Backtests({ rows, onRun, canRun }: { rows: SetupBacktestView[]; onRun: () => void; canRun: boolean }) {
  return (
    <Card
      title="The setups and their track record"
      subtitle="Each setup is tested on 5+ years of past prices for the whole trading universe, with Groww's full charges and slippage. A setup that lost money after costs is switched OFF and never produces ideas."
    >
      <div className="grid gap-4">
        {rows.map((b) => (
          <div key={b.setup} className="rounded-xl border border-border bg-surface p-4 text-sm leading-relaxed shadow-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-display text-[15px] font-semibold">{b.label}</span>
              {!b.tested ? <Badge>Not tested yet</Badge> : b.allowed ? <Badge tone="good">✓ ON</Badge> : <Badge tone="bad">✕ OFF</Badge>}
            </div>
            <p className="mt-1.5 text-muted">{b.plain}</p>
            <p className="mt-1">{b.verdict}</p>
            {b.stats && b.stats.trades > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Stat label="Past trades" value={b.stats.trades.toLocaleString("en-IN")} note={b.stats.period ? `${fmtDate(b.stats.period[0])} – ${fmtDate(b.stats.period[1])}` : undefined} />
                <Stat
                  label="Won"
                  value={pct0(b.stats.win_rate)}
                  note={b.stats.max_losing_streak !== undefined ? `worst losing run: ${b.stats.max_losing_streak}` : undefined}
                />
                <Stat
                  label="Average per trade"
                  value={rFmt(b.stats.avg_r)}
                  tone={sign(b.stats.avg_r)}
                  note={
                    b.stats.avg_r_before_charges !== undefined
                      ? `${rFmt(b.stats.avg_r_before_charges)} before charges · avg charges ${inr(b.stats.avg_charges ?? 0)}`
                      : b.stats.avg_charges !== undefined
                        ? `avg charges ${inr(b.stats.avg_charges)}`
                        : undefined
                  }
                />
                {b.portfolio && (
                  <Stat
                    label={`${inr(b.portfolio.capital)} would have become`}
                    value={inr(b.portfolio.final_equity)}
                    note={
                      b.portfolio.ruined_on
                        ? `all of it lost by ${fmtDate(b.portfolio.ruined_on)}`
                        : `${(b.portfolio.cagr * 100).toFixed(1)}%/yr · worst dip ${(b.portfolio.max_drawdown * 100).toFixed(0)}%`
                    }
                  />
                )}
              </div>
            )}
          </div>
        ))}
        <p className="text-xs leading-relaxed text-muted">
          <b>R</b> = the amount you risked on a trade. +2R means you made twice what you risked; −1R means the stop-loss was hit. Past results
          include survivorship bias (today&apos;s most-traded stocks look better in hindsight) and don&apos;t guarantee future returns.
        </p>
        <div>
          <Button variant="secondary" onClick={onRun} disabled={!canRun}>
            Re-run backtests now
          </Button>
        </div>
      </div>
    </Card>
  );
}

type CostDrag = {
  assumptions: string;
  your_capital: number;
  rows: { capital: number; qty: number; position?: number; at_risk?: number; charges?: number; charges_in_r?: number; breakeven_win_rate?: number; note?: string }[];
};

function CostDragCard() {
  const [data, setData] = useState<CostDrag | null>(null);
  useEffect(() => {
    api.get<CostDrag>("/trading/cost-drag").then(setData, () => {});
  }, []);
  if (!data) return null;
  return (
    <Card
      title="What charges do to small trades"
      subtitle="Groww's charges are partly fixed (minimum brokerage, ₹23.6 DP charge per sale), so they weigh much more on small trades. Without any charges, a 2:1 reward-to-risk trade breaks even at a 33% win rate."
    >
      <div className="overflow-x-auto">
        <table className="nm-table min-w-[560px]">
          <thead>
            <tr>
              <th>Trading capital</th>
              <th className="text-right">At risk per trade</th>
              <th className="text-right">Charges (buy + sell)</th>
              <th className="text-right">Charges ÷ risk</th>
              <th className="text-right">Win rate needed to break even</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.capital} className={r.capital === data.your_capital ? "!bg-brand-soft" : ""}>
                <td className="num font-medium">
                  {inr(r.capital)} {r.capital === data.your_capital && <Badge tone="brand">yours</Badge>}
                </td>
                {r.qty ? (
                  <>
                    <td className="num text-right">{inr(r.at_risk!)}</td>
                    <td className="num text-right">{rupee(r.charges!)}</td>
                    <td className="num text-right">{r.charges_in_r!.toFixed(2)}R</td>
                    <td className="num text-right font-semibold">{pct0(r.breakeven_win_rate)}</td>
                  </>
                ) : (
                  <td colSpan={4} className="text-muted">
                    {r.note}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-muted">{data.assumptions}</p>
    </Card>
  );
}

function TradingPage() {
  const [ov, setOv] = useState<TradingOverview | null>(null);
  const [ideas, setIdeas] = useState<TradingIdea[]>([]);
  const [paper, setPaper] = useState<PaperSummary | null>(null);
  const [bts, setBts] = useState<SetupBacktestView[]>([]);
  const [capitalDraft, setCapitalDraft] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      Promise.all([
        api.get<TradingOverview>("/trading/overview"),
        api.get<TradingIdea[]>("/trading/ideas"),
        api.get<PaperSummary>("/trading/paper"),
        api.get<SetupBacktestView[]>("/trading/backtests"),
      ]).then(
        ([o, i, p, b]) => {
          setOv(o);
          setIdeas(i);
          setPaper(p);
          setBts(b);
        },
        (e) => setError(e instanceof Error ? e.message : "Couldn't load"),
      ),
    [],
  );

  useEffect(() => {
    load();
  }, [load]);

  async function saveCapital() {
    if (!capitalDraft) return;
    try {
      await api.patch("/settings", { trading_paper_capital: capitalDraft });
      setMsg("Saved. New ideas will be sized for this amount. Use “Start a fresh practice account” to restart your record with it.");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Couldn't save");
    }
  }

  async function reset() {
    const ok = await confirmDialog({
      title: "Start a fresh practice account?",
      body: "This practice account is closed and a new one starts with your practice capital. Past trades stay in your history.",
      confirmLabel: "Start fresh",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await api.post("/trading/paper/reset");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Couldn't reset");
    }
  }

  async function runBacktests() {
    await api.post("/data/jobs/stock_backtests/run");
    setMsg("Backtests started. They take a few minutes; refresh this page afterwards.");
  }

  if (error) return <Notice tone="bad">{error}</Notice>;
  if (!ov || !paper) return <PageSkeleton cards={3} label="Loading trading" />;

  const st = ov.state;
  const noData = !ov.data.latest_session;
  const blockedReason = st.cooling_off_reason || st.loss_limit_reason;
  const openTrades = paper.trades.filter((t) => t.status === "pending" || t.status === "open");
  const pastTrades = paper.trades.filter((t) => !(t.status === "pending" || t.status === "open"));

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Practice mode"
        title="Short-term trading"
        description={
          <>
            Daily ideas from tested setups, traded with <b>pretend money</b> ({inr(st.capital)}). Delivery trades held for days, never intraday.
            Nivesh Mitra never places orders.
          </>
        }
      />

      <Notice tone="warn">
        <b>Practice mode.</b>{" "}
        {ov.practice.ends_on ? `Your practice period ends on ${fmtDate(ov.practice.ends_on)}.` : ""} Real-money trading stays locked until:
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          {ov.real_money_locked.length ? ov.real_money_locked.map((r) => <li key={r}>{r}</li>) : <li>Nothing — but keep it small and capped.</li>}
        </ul>
      </Notice>

      {noData && (
        <Card title="Waiting for price data from Groww" subtitle="Ideas and backtests need daily price history for the most-traded NSE stocks, which comes from your Groww API.">
          {ov.data.prices_error && (
            <div className="mb-3">
              <Notice tone="bad">{ov.data.prices_error}</Notice>
            </div>
          )}
          <GrowwCheck />
        </Card>
      )}

      {blockedReason && <Notice tone="bad">{blockedReason}</Notice>}

      <section className="grid gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-xl font-semibold">
            {ov.ideas_status?.for_session ? `Ideas for ${fmtDate(ov.ideas_status.for_session)}` : "Today's ideas"}
          </h2>
          {ov.data.latest_session && <span className="text-xs text-muted">from closing prices of {fmtDate(ov.data.latest_session)}</span>}
        </div>
        {ideas.length ? (
          ideas.map((i) => <IdeaCard key={i.id} idea={i} onBought={load} />)
        ) : (
          <Card>
            <div className="flex items-start gap-3.5">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-navy text-ink-accent">
                <IconPause />
              </span>
              <div>
                <p className="font-display text-lg font-semibold">No trade today</p>
                <p className="mt-1 text-sm leading-relaxed text-muted">
                  {ov.ideas_status?.reason ??
                    (noData ? "Ideas appear here each evening once Groww price data is available." : "Ideas are made each evening after the market closes.")}{" "}
                  Not buying is a valid decision.
                </p>
              </div>
            </div>
          </Card>
        )}
      </section>

      <Card title="Your practice account" subtitle={`Started ${fmtDate(paper.started)} with ${inr(paper.start_capital)}`}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Value now" value={inr(paper.equity)} note={`${signedRupee(paper.equity - paper.start_capital)} overall`} tone={sign(paper.equity - paper.start_capital)} />
          <Stat label="Closed trades" value={paper.closed_trades} note={`${st.open_positions} open of max ${st.max_open_positions}`} />
          <Stat label="Won" value={pct0(paper.win_rate)} />
          <Stat label="Average per trade" value={rFmt(paper.avg_r)} tone={sign(paper.avg_r)} />
          <Stat label="Charges paid" value={inr(paper.charges_paid)} note="real-money trades would pay these" />
        </div>
        <h3 className="mb-2.5 mt-7 text-[15px] font-semibold">Open and waiting</h3>
        <TradesTable trades={openTrades} onAction={load} />
        <h3 className="mb-2.5 mt-7 text-[15px] font-semibold">History</h3>
        <TradesTable trades={pastTrades} onAction={load} />
        <div className="mt-7 flex flex-wrap items-center gap-2.5 border-t border-border pt-5 text-sm">
          <label className="flex items-center gap-2 font-medium">
            Practice capital (₹)
            <input
              type="number"
              min={1000}
              step={1000}
              className={`${inputClass} w-36 font-normal`}
              defaultValue={st.capital}
              onChange={(e) => setCapitalDraft(Number(e.target.value))}
            />
          </label>
          <Button variant="secondary" onClick={saveCapital} disabled={!capitalDraft}>
            Save
          </Button>
          <Button variant="danger" onClick={reset}>
            Start a fresh practice account
          </Button>
        </div>
        {msg && (
          <p role="status" className="mt-3 text-xs leading-relaxed text-muted">
            {msg}
          </p>
        )}
      </Card>

      <CostDragCard />

      <Backtests rows={bts} onRun={runBacktests} canRun={!noData} />

      <IntradaySetups />
    </div>
  );
}

function IntradaySetups() {
  const [rows, setRows] = useState<IntradaySetupView[] | null>(null);
  useEffect(() => {
    api.get<IntradaySetupView[]>("/trading/intraday").then(setRows, () => setRows([]));
  }, []);
  if (!rows) return null;
  return (
    <Card
      title="Same-day (intraday) strategies"
      subtitle="Buy in the morning, sell by 3:00 PM. Long only, no borrowed money. Each setup was fixed before any testing, built on 2020–23 prices and judged only on 2024 onwards, with Groww's intraday charges and cautious fills."
    >
      <div className="grid gap-4">
        {rows.map((b) => (
          <div key={b.setup} className="rounded-xl border border-border bg-surface p-4 text-sm leading-relaxed shadow-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-display text-[15px] font-semibold">{b.label}</span>
              {!b.tested ? <Badge>Not tested yet</Badge> : b.allowed ? <Badge tone="good">✓ ON</Badge> : <Badge tone="bad">✕ OFF</Badge>}
            </div>
            <p className="mt-1.5 text-muted">{b.plain}</p>
            <p className="mt-1">{b.verdict}</p>
            {b.test && b.test.trades > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Stat label="Trades since 2024" value={b.test.trades.toLocaleString("en-IN")} note={b.build ? `${b.build.trades.toLocaleString("en-IN")} in 2020–23` : undefined} />
                <Stat label="Won" value={pct0(b.test.win_rate)} />
                <Stat
                  label="Average per trade"
                  value={rFmt(b.test.avg_r)}
                  tone={sign(b.test.avg_r)}
                  note={b.test.avg_r_before_charges !== undefined ? `${rFmt(b.test.avg_r_before_charges)} before charges` : undefined}
                />
                <Stat
                  label="With ₹1 lakh instead"
                  value={rFmt(b.test_avg_r_at_1_lakh)}
                  tone={sign(b.test_avg_r_at_1_lakh)}
                  note="charges weigh less on bigger trades"
                />
              </div>
            )}
          </div>
        ))}
        <p className="text-xs leading-relaxed text-muted">
          SEBI&apos;s study of individual intraday traders found most of them lose money. A setup is switched ON only if it made money after
          charges on data it was never tuned on; otherwise the app shows no same-day ideas.
        </p>
      </div>
    </Card>
  );
}

export default function Page() {
  return (
    <AppShell>
      <TradingPage />
    </AppShell>
  );
}
