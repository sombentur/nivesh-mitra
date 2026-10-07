"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { AllocationBar } from "@/components/AllocationBar";
import { AppShell, useMe } from "@/components/AppShell";
import { DayStrip } from "@/components/dashboard/DayStrip";
import { HorizonPicks } from "@/components/dashboard/HorizonPicks";
import { MarketCard } from "@/components/dashboard/MarketCard";
import { NewsPulse } from "@/components/dashboard/NewsPulse";
import { BreadthCard, IndexWidgets, StockSnaps, useMarket } from "@/components/dashboard/MarketWidgets";
import { StockIdeas } from "@/components/dashboard/StockIdeas";
import { DataStrip, useDataStatus } from "@/components/DataHealth";
import { IconArrowRight, IconChevronDown, IconLayers, IconPulse, IconTrend, IconWallet } from "@/components/icons";
import { EmergencyMeter } from "@/components/ProfileSummary";
import { TradingCalendar } from "@/components/TradingCalendar";
import { Badge, Card, DISCLAIMER, Eyebrow, LinkMore, Skeleton, SkeletonLines, Stat } from "@/components/ui";
import {
  api,
  type Dashboard,
  type DataStatus,
  type Goal,
  type IntradaySetupView,
  type PaperSummary,
  type Plan,
  type ProfileView,
  type SecretStatus,
  type SetupBacktestView,
  type TradingIdea,
  type TradingOverview,
} from "@/lib/api";
import { fmtDate, fmtDay, inr, shortFundName, signedPct, titleCase } from "@/lib/format";
import { SIDEBAR_QUERY, useMediaQuery } from "@/lib/useMediaQuery";

type StepState = "done" | "running" | "partial" | "next" | "planned";

function roadmap(stockReady: boolean): [string, StepState][] {
  return [
    ["Foundation: setup, secure login, encrypted keys", "done"],
    ["Onboarding: risk profile and asset split", "done"],
    ["Mutual fund data: AMFI + mfapi.in", "done"],
    ["Groww read-only connection + stock prices", "done"],
    ["Trading setups, backtests with full costs", stockReady ? "done" : "running"],
    ["Daily trade ideas + practice (paper) trading", stockReady ? "done" : "running"],
    ["Mutual fund engine: scores, SIP and goal plan", "done"],
    ["CAS import: your mutual fund holdings", "next"],
    ["Stock engine: fundamentals, Trendlyne red flags", "planned"],
    ["Risk engine on every recommendation", "planned"],
    ["Explanations: templates + Claude", "planned"],
    ["Dashboard, morning brief, weekly review", "partial"],
    ["Scorecard of every recommendation", "planned"],
  ];
}

const HERO_TONE = { good: "text-ink-up", warn: "text-ink-gold", bad: "text-ink-down", neutral: "text-white" };

function HeroTile({ icon, label, value, note, tone = "neutral", href }: {
  icon: ReactNode;
  label: string;
  value: ReactNode | null; // null while loading
  note: ReactNode;
  tone?: keyof typeof HERO_TONE;
  href: string;
}) {
  return (
    <Link href={href} className="glass-ink group rounded-2xl p-4 hover:bg-white/[0.12] focus-visible:outline-ink-accent">
      <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-muted">
        <span className="text-ink-accent">{icon}</span> {label}
      </p>
      {value === null ? (
        <Skeleton className="mt-3 h-6 w-32" />
      ) : (
        <p className={`mt-2 font-display text-xl font-semibold tracking-tight ${HERO_TONE[tone]}`}>{value}</p>
      )}
      <p className="mt-1 flex items-center justify-between gap-2 text-xs text-ink-muted">
        <span>{note}</span>
        <IconArrowRight width={14} height={14} className="shrink-0 -translate-x-1 opacity-0 transition duration-200 group-hover:translate-x-0 group-hover:opacity-100" />
      </p>
    </Link>
  );
}

function Hero({ dash, overview, ideas, plan, view }: {
  dash: Dashboard | null;
  overview: TradingOverview | null;
  ideas: TradingIdea[] | null;
  plan: Plan | null;
  view: ProfileView | null;
}) {
  const me = useMe();
  const now = new Date();
  const hour = now.getHours();
  const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const session = overview?.ideas_status?.for_session ?? ideas?.[0]?.for_session ?? null;
  const blocked = overview?.state.cooling_off_reason || overview?.state.loss_limit_reason;
  const market = dash?.market ?? null;
  const sipTotal = plan?.sips.reduce((s, x) => s + x.monthly_affordable, 0) ?? 0;
  const emergencyFirst = view?.result.emergency.first_action || (plan?.emergency?.monthly ?? 0) > 0;

  return (
    <section className="ink-panel on-ink relative overflow-hidden rounded-3xl p-6 shadow-lift sm:p-8">
      {/* a rising line in the corner, echoing the arrow in the logo */}
      <svg viewBox="0 0 400 200" preserveAspectRatio="none" className="pointer-events-none absolute inset-y-0 right-0 hidden h-full w-1/2 opacity-40 sm:block" aria-hidden="true">
        <path d="M0,180 L50,160 L95,170 L150,130 L200,142 L255,96 L300,108 L350,58 L400,24" fill="none" stroke="var(--ink-accent)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        <path d="M0,180 L50,160 L95,170 L150,130 L200,142 L255,96 L300,108 L350,58 L400,24 L400,200 L0,200 Z" fill="var(--ink-accent)" opacity="0.07" />
      </svg>
      <div className="relative">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-accent">
          {now.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
        </p>
        <h1 className="mt-2 text-[28px] font-semibold leading-tight text-white sm:text-4xl">
          {hello}
          {me?.name ? `, ${me.name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1.5 text-sm text-ink-muted">Today&apos;s decisions at a glance. You place any order yourself on Groww.</p>

        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <HeroTile
            href="/trading"
            icon={<IconTrend width={15} height={15} />}
            label={session ? `Stocks · ${fmtDay(session)}` : "Stocks · next session"}
            value={ideas === null ? null : blocked ? "Paused" : ideas.length ? `${ideas.length} practice idea${ideas.length > 1 ? "s" : ""}` : "No trade"}
            tone={blocked ? "warn" : ideas?.length ? "good" : "neutral"}
            note={blocked ? "risk rule: cooling off" : ideas?.length ? `best: ${ideas[0].symbol}` : "no setup passed every rule"}
          />
          <HeroTile
            href="/plan"
            icon={<IconLayers width={15} height={15} />}
            label="Mutual funds"
            value={emergencyFirst ? "Emergency fund first" : sipTotal ? `${inr(sipTotal)}/month` : plan ? "No SIP needed" : null}
            tone={emergencyFirst ? "warn" : "neutral"}
            note={
              emergencyFirst && plan?.emergency?.fund
                ? `into ${shortFundName(plan.emergency.fund.name)}`
                : plan
                  ? `${plan.sips.length} SIP${plan.sips.length === 1 ? "" : "s"} for your goals`
                  : "your plan"
            }
          />
          <HeroTile
            href="/trading"
            icon={<IconPulse width={15} height={15} />}
            label="Market mood"
            value={market ? market.mood : dash ? "—" : null}
            tone={market?.tone ?? "neutral"}
            note={market ? `Nifty ${market.nifty.toLocaleString("en-IN", { maximumFractionDigits: 0 })} (${signedPct(market.change_pct, 2)})` : "waiting for prices"}
          />
        </div>
      </div>
    </section>
  );
}

function PlanCard({ plan, view, planError }: { plan: Plan | null; view: ProfileView | null; planError: boolean }) {
  const e = plan?.emergency;
  const building = !!e && e.monthly > 0;
  return (
    <Card
      title="Your monthly plan"
      subtitle={view ? `${titleCase(view.result.final_category)} investor` : undefined}
      action={<LinkMore href="/plan">Open</LinkMore>}
    >
      {plan ? (
        <>
          <Stat label="You invest each month" value={<span className="text-[26px] tracking-tight">{inr(plan.budget.investable)}</span>} />
          {building && e && (
            <div className="mt-4 rounded-xl bg-warn-soft p-3.5 ring-1 ring-inset ring-warn/25">
              <p className="flex items-center justify-between gap-3 text-sm">
                <span className="font-semibold">Emergency fund first</span>
                <span className="num font-semibold">{inr(e.monthly)}/mo</span>
              </p>
              <p className="mt-0.5 text-xs text-muted">into {e.fund ? shortFundName(e.fund.name) : "a liquid fund"}</p>
              <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-surface">
                <div className="h-full rounded-full bg-warn transition-[width] duration-700" style={{ width: `${Math.min(100, (e.current / e.target) * 100)}%` }} />
              </div>
              <p className="num mt-1.5 text-xs text-muted">
                {inr(e.current)} of {inr(e.target)}
                {e.months_to_complete ? ` · full in about ${e.months_to_complete} months` : ""}
              </p>
            </div>
          )}
          <div className="mt-5">
            <Eyebrow>Goal SIPs</Eyebrow>
          </div>
          <ul className="mt-2 grid grid-cols-1 gap-2">
            {plan.sips.slice(0, 5).map((s) => (
              <li key={s.fund.scheme_code} className="flex items-center justify-between gap-3 rounded-xl bg-surface-2 px-3.5 py-2.5 text-sm ring-1 ring-inset ring-border">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{shortFundName(s.fund.name)}</span>
                  <span className="block truncate text-xs text-muted">for {s.goals.join(", ")}</span>
                </span>
                {s.monthly_affordable > 0 ? (
                  <span className="num shrink-0 font-semibold">{inr(s.monthly_affordable)}</span>
                ) : (
                  <span className="shrink-0 text-right text-[11px] leading-tight text-muted">
                    needs <span className="num">{inr(s.monthly_needed)}</span>/mo
                    <br />
                    starts later
                  </span>
                )}
              </li>
            ))}
          </ul>
          {plan.notes[0] && <p className="mt-3 text-xs leading-relaxed text-muted">{plan.notes[0]}</p>}
        </>
      ) : planError ? (
        <p className="text-sm text-muted">Your plan appears once fund scores are ready.</p>
      ) : (
        <div className="grid gap-4">
          <Skeleton className="h-8 w-40" />
          <SkeletonLines lines={4} label="Loading your plan" />
        </div>
      )}
      {view && (
        <div className="mt-5 border-t border-border pt-4">
          <Eyebrow>Your split</Eyebrow>
          <div className="mt-3">
            <AllocationBar
              split={view.allocation.effective}
              caption={view.allocation.trading_locked ? "Trading is locked for now (practice first). Its share stays in mutual funds." : undefined}
            />
          </div>
        </div>
      )}
    </Card>
  );
}

function PracticeCard({ overview, paper }: { overview: TradingOverview | null; paper: PaperSummary | null }) {
  if (!overview) return null;
  const pnl = paper ? paper.equity - paper.start_capital : overview.state.realized_pnl;
  return (
    <Card
      title="Practice account"
      subtitle="Pretend money: learn the rules before real money"
      action={<LinkMore href="/trading">Open</LinkMore>}
    >
      <div className="flex items-end justify-between gap-3">
        <Stat label="Value" value={<span className="text-[26px] tracking-tight">{inr(paper?.equity ?? overview.state.capital)}</span>} />
        <Stat label="Profit / loss" value={`${pnl > 0 ? "+" : pnl < 0 ? "−" : ""}${inr(Math.abs(pnl))}`} tone={pnl > 0 ? "good" : pnl < 0 ? "bad" : undefined} />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3">
        <Stat label="Open trades" value={`${overview.state.open_positions} / ${overview.state.max_open_positions}`} />
        <Stat label="Closed" value={paper?.closed_trades ?? 0} />
        <Stat label="Days left" value={overview.practice.complete ? "Done" : overview.practice.days_left} hint={overview.practice.ends_on ? `ends ${fmtDate(overview.practice.ends_on)}` : undefined} />
      </div>
    </Card>
  );
}

function SafetyCard({ view, goals }: { view: ProfileView | null; goals: Goal[] }) {
  if (!view) return null;
  return (
    <Card
      title="Safety net & goals"
      action={<LinkMore href="/profile">Edit</LinkMore>}
    >
      <EmergencyMeter e={view.result.emergency} targetMonths={6} showAction={false} />
      <div className="mt-5 border-t border-border pt-4">
        <Eyebrow>Goals · amounts include inflation</Eyebrow>
        {goals.length === 0 ? (
          <p className="mt-2 text-sm text-muted">
            No goals yet. <Link href="/profile" className="font-medium text-brand-strong underline-offset-2 hover:underline">Add one</Link>.
          </p>
        ) : (
          <ul className="mt-2 grid divide-y divide-border text-sm">
            {goals.map((g) => (
              <li key={g.id} className="flex justify-between gap-3 py-2">
                <span>
                  {g.name} <span className="text-muted">· {g.target_year}</span>
                </span>
                <span className="num font-medium">{inr(g.target_amount_future)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function SystemStatus({ status, overview }: { status: DataStatus | null; overview: TradingOverview | null }) {
  const [secrets, setSecrets] = useState<SecretStatus[] | null>(null);
  useEffect(() => {
    api.get<SecretStatus[]>("/settings/secrets").then(setSecrets, () => setSecrets([]));
  }, []);
  const isSet = (name: string) => secrets?.find((s) => s.name === name)?.is_set ?? false;
  const growwSaved = isSet("groww_totp_token") && isSet("groww_totp_secret");
  const stockReady = !!status?.jobs.find((j) => j.name === "stock_backtests")?.last_success;
  const rows: [string, ReactNode][] = [
    ["Google sign-in + authenticator app", <Badge key="g" tone="good">Connected</Badge>],
    [
      "Groww (read-only)",
      !growwSaved ? (
        <Badge key="gr">Not set</Badge>
      ) : overview?.data.prices_ok ? (
        <Badge key="gr" tone="good">Working · prices up to date</Badge>
      ) : overview?.data.prices_error ? (
        <Badge key="gr" tone="bad">Problem · test in Settings</Badge>
      ) : (
        <Badge key="gr">Saved</Badge>
      ),
    ],
    ["Trendlyne MCP", isSet("trendlyne_mcp_url") ? <Badge key="t" tone="good">Saved</Badge> : <Badge key="t">Not set</Badge>],
    ["Claude API (optional)", isSet("anthropic_api_key") ? <Badge key="c" tone="good">Saved</Badge> : <Badge key="c">Optional</Badge>],
  ];
  return (
    <details className="group rounded-2xl border border-border bg-surface shadow-card">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-2xl p-5 hover:bg-surface-2/60 sm:px-6">
        <span>
          <span className="block font-display text-base font-semibold">Connections, data &amp; build progress</span>
          <span className="mt-1 block">
            <DataStrip status={status} />
          </span>
        </span>
        <IconChevronDown className="shrink-0 text-muted transition group-open:rotate-180" />
      </summary>
      <div className="grid grid-cols-1 gap-6 border-t border-border p-5 sm:p-6 lg:grid-cols-2">
        <div>
          <Eyebrow>Connections</Eyebrow>
          <ul className="mt-3 grid gap-3 text-sm">
            {rows.map(([label, badge]) => (
              <li key={label} className="flex items-center justify-between gap-3">
                <span>{label}</span>
                {secrets === null ? <Badge>…</Badge> : badge}
              </li>
            ))}
          </ul>
          <div className="mt-4">
            <LinkMore href="/settings">Settings</LinkMore>
          </div>
        </div>
        <div>
          <Eyebrow>Build progress · Phase 1</Eyebrow>
          <ol className="mt-3 grid gap-2 text-sm">
            {roadmap(stockReady).map(([label, state], i) => (
              <li key={label} className="flex items-center gap-3">
                <span className="num w-5 text-right text-xs text-muted">{i + 1}</span>
                <span className={`flex-1 ${state === "planned" ? "text-muted" : ""}`}>{label}</span>
                {state === "done" && <Badge tone="good">Done</Badge>}
                {state === "running" && <Badge tone="warn">Built · downloading data</Badge>}
                {state === "partial" && <Badge tone="brand">Dashboard done</Badge>}
                {state === "next" && <Badge tone="gold">Next</Badge>}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </details>
  );
}

function Home() {
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [overview, setOverview] = useState<TradingOverview | null>(null);
  const [ideas, setIdeas] = useState<TradingIdea[] | null>(null);
  const [paper, setPaper] = useState<PaperSummary | null>(null);
  const [view, setView] = useState<ProfileView | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planError, setPlanError] = useState(false);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [setups, setSetups] = useState<SetupBacktestView[]>([]);
  const [intraday, setIntraday] = useState<IntradaySetupView[]>([]);
  const { status } = useDataStatus(10000);
  const { snap } = useMarket();
  const hasSidebar = useMediaQuery(SIDEBAR_QUERY);

  useEffect(() => {
    api.get<Dashboard>("/dashboard").then(setDash, () => setDash({ market: null, horizons: [] }));
    api.get<TradingOverview>("/trading/overview").then(setOverview, () => {});
    api.get<TradingIdea[]>("/trading/ideas").then(setIdeas, () => setIdeas([]));
    api.get<PaperSummary>("/trading/paper").then(setPaper, () => {});
    api.get<ProfileView>("/profile").then(setView, () => {});
    api.get<Plan>("/plan").then(setPlan, () => setPlanError(true));
    api.get<Goal[]>("/goals").then(setGoals, () => {});
    api.get<SetupBacktestView[]>("/trading/backtests").then(setSetups, () => {});
    api.get<IntradaySetupView[]>("/trading/intraday").then(setIntraday, () => {});
  }, []);

  return (
    <div className="grid grid-cols-1 gap-6">
      <Hero dash={dash} overview={overview} ideas={ideas} plan={plan} view={view} />

      <DayStrip days={dash?.days} />

      <IndexWidgets snap={snap} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="xl:col-span-7">
          <StockIdeas ideas={ideas} overview={overview} status={status} setups={setups} intraday={intraday} />
        </div>
        <div className="xl:col-span-5">
          <MarketCard market={dash?.market ?? null} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="xl:col-span-8">
          <StockSnaps snap={snap} />
        </div>
        <div className="xl:col-span-4">
          <BreadthCard snap={snap} />
        </div>
      </div>

      {!hasSidebar && <TradingCalendar className="rounded-2xl border border-border bg-surface p-4 shadow-card sm:p-5" />}

      <NewsPulse />

      {dash ? (
        <HorizonPicks horizons={dash.horizons} />
      ) : (
        <Card title="Which mutual fund, for how long?">
          <SkeletonLines lines={4} label="Loading fund picks" />
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <PlanCard plan={plan} view={view} planError={planError} />
        <PracticeCard overview={overview} paper={paper} />
        <SafetyCard view={view} goals={goals} />
      </div>

      <p className="flex items-start gap-2.5 rounded-xl border border-border bg-surface/70 px-4 py-3 text-xs leading-relaxed text-muted">
        <IconWallet className="mt-0.5 shrink-0 text-brand" width={15} height={15} />
        {DISCLAIMER} Stock ideas are practice (paper) trades until your practice period ends. Fund picks and returns are based on past data.
      </p>

      <SystemStatus status={status} overview={overview} />
    </div>
  );
}

export default function Page() {
  return (
    <AppShell>
      <Home />
    </AppShell>
  );
}
