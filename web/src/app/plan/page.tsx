"use client";

import Link from "next/link";
import { GrowwButton } from "@/components/GrowwButton";
import { useEffect, useState, type FormEvent } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, DISCLAIMER, inputClass, Notice, PageHeader, PageSkeleton, StatTile } from "@/components/ui";
import { api, ApiError, type Plan, type PlanFund, type PlanGoal, type SipCalcResult } from "@/lib/api";
import { fmtDate, inr, titleCase } from "@/lib/format";

const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`);

function FundLine({ f, monthly, note }: { f: PlanFund; monthly?: number; note?: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <Link href={`/funds/${f.scheme_code}`} className="rounded font-display text-[15px] font-semibold hover:text-brand-strong hover:underline">
          {f.name}
        </Link>
        <div className="mt-0.5 text-xs leading-relaxed text-muted">
          {f.category} · score {f.score?.toFixed(0) ?? "—"} (#{f.rank} of {f.peers}, {f.confidence} confidence) · cost {pct(f.ter, 2)} a year
          {f.rr5_med !== null && ` · typical 5-yr return ${pct(f.rr5_med)}`}
        </div>
        {note && <div className="mt-0.5 text-xs leading-relaxed text-muted">{note}</div>}
      </div>
      {monthly !== undefined && <div className="num text-right text-lg font-semibold tracking-tight">{inr(monthly)}/mo</div>}
    </div>
  );
}

function Steps({ steps, title = "What to do on Groww" }: { steps: string[]; title?: string }) {
  if (!steps.length) return null;
  return (
    <details className="group/d rounded-xl border border-border bg-surface-2/50 px-3.5 py-2.5 text-sm open:bg-surface">
      <summary className="flex list-none items-center justify-between gap-2 rounded font-medium hover:text-brand-strong">
        {title} <span className="text-muted transition-transform duration-200 group-open/d:rotate-180">⌄</span>
      </summary>
      <ol className="mt-2 list-decimal space-y-1.5 pl-5 leading-relaxed text-muted">
        {steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
    </details>
  );
}

function GoalCard({ g }: { g: PlanGoal }) {
  const [cons, exp, opt] = g.projection_if_recommended;
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-2">
          {g.name} <Badge>{g.target_year}</Badge>
          <span className="text-sm font-normal text-muted">
            about {g.years_away} {g.years_away === 1 ? "year" : "years"} away · {g.equity_share}% in shares
          </span>
        </span>
      }
      subtitle={`Target ${inr(g.target_today)} in today's money ≈ ${inr(g.target_future)} by then (with inflation)${g.current_corpus ? `; already saved ${inr(g.current_corpus)}` : ""}.`}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Recommended SIP" value={`${inr(g.recommended_sip)}/mo`} hint="planned with cautious returns" />
        <StatTile label="If markets do normally" value={`${inr(g.sip_needed.expected)}/mo`} hint="would be enough" />
        <StatTile
          label="Affordable right now"
          value={`${inr(g.affordable_now)}/mo`}
          tone={g.affordable_now < g.recommended_sip ? "warn" : "good"}
          hint="after the emergency fund and higher-priority goals"
        />
        <StatTile
          label="With the recommended SIP you'd have"
          size="md"
          value={`${inr(cons)} – ${inr(opt)}`}
          hint={`cautious → good markets (normal ≈ ${inr(exp)})`}
        />
      </div>
      <div className="mt-5 grid gap-3">
        {g.funds.map((f) => (
          <div key={f.slot} className="rounded-xl border border-border bg-surface p-3.5 shadow-xs">
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
              {f.label} · {f.share}%
            </div>
            {f.fund ? (
              <FundLine
                f={f.fund}
                monthly={f.monthly}
                note={f.regular_would_cost_10y ? `Choosing its Regular plan instead would cost about ${inr(f.regular_would_cost_10y)} over 10 years.` : undefined}
              />
            ) : (
              <p className="text-sm text-muted">No scored fund available for this slot yet.</p>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function SipCalculator({ mix }: { mix: Record<string, number> }) {
  const [monthly, setMonthly] = useState(5000);
  const [years, setYears] = useState(10);
  const [stepUp, setStepUp] = useState(0);
  const [res, setRes] = useState<SipCalcResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(e?: FormEvent) {
    e?.preventDefault(); // Enter in a field submits the form; the button calls run() directly
    try {
      setRes(await api.post<SipCalcResult>("/plan/sip-calculator", { monthly, years, step_up: stepUp / 100, mix }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't calculate");
    }
  }

  return (
    <Card title="SIP calculator" subtitle="Uses the same mix as your long-term goals and the same cautious / normal / good return assumptions.">
      <form onSubmit={run} className="flex flex-wrap items-end gap-3 text-sm font-medium">
        <label className="grid gap-1.5">
          Monthly SIP (₹)
          <input type="number" min={100} step={500} className={`${inputClass} w-36 font-normal`} value={monthly} onChange={(e) => setMonthly(Number(e.target.value))} />
        </label>
        <label className="grid gap-1.5">
          Years
          <input type="number" min={1} max={50} className={`${inputClass} w-24 font-normal`} value={years} onChange={(e) => setYears(Number(e.target.value))} />
        </label>
        <label className="grid gap-1.5">
          Increase each year (%)
          <input type="number" min={0} max={50} className={`${inputClass} w-28 font-normal`} value={stepUp} onChange={(e) => setStepUp(Number(e.target.value))} />
        </label>
        <Button type="button" onClick={() => run()}>
          Calculate
        </Button>
      </form>
      {error && (
        <div className="mt-4">
          <Notice tone="bad">{error}</Notice>
        </div>
      )}
      {res && (
        <div className="nm-enter mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {res.scenarios.map((s) => (
            <StatTile
              key={s.scenario}
              label={`${s.scenario === "conservative" ? "Cautious" : s.scenario === "expected" ? "Normal" : "Good"} markets · ${pct(s.rate)} a year`}
              value={inr(s.value)}
              hint={`you put in ${inr(s.invested)}`}
              className={s.scenario === "expected" ? "!bg-brand-soft !ring-brand/25" : ""}
            />
          ))}
          <p className="text-xs leading-relaxed text-muted sm:col-span-3">{res.note}</p>
        </div>
      )}
    </Card>
  );
}

function PlanPage() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<Plan>("/plan").then(setPlan, (e) => setError(e instanceof ApiError && e.status === 409 ? e.message : e.message));
  }, []);

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (!plan) return <PageSkeleton cards={3} label="Working out your plan" />;

  const b = plan.budget;
  const longGoal = plan.goals.find((g) => g.years_away >= 5);
  return (
    <div className="grid gap-6">
      <PageHeader
        title="My plan"
        description={
          <>
            For a <b>{titleCase(plan.profile)}</b> investor, using the best-scored Direct funds (scores as of {fmtDate(plan.scores_as_of)}). You set up
            every SIP yourself on Groww — Nivesh Mitra never invests for you.
          </>
        }
      />

      <Card title="Where your monthly money goes">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {[
            ["You can invest", b.investable],
            ["Emergency fund", b.to_emergency_fund],
            ["Mutual fund SIPs", b.for_mutual_funds],
            ["Stocks (your split)", b.for_stocks],
            ["Your goals need", b.goals_need],
          ].map(([label, v], i) => (
            <StatTile key={label as string} label={label} value={`${inr(v as number)}/mo`} className={i === 0 ? "col-span-2 !bg-brand-soft !ring-brand/25 sm:col-span-1" : ""} />
          ))}
        </div>
        {plan.notes.map((n) => (
          <div key={n} className="mt-3">
            <Notice tone="warn">{n}</Notice>
          </div>
        ))}
      </Card>

      {plan.emergency && (
        <Card title="Step 1 · Build your emergency fund" subtitle={`Target ${inr(plan.emergency.target)} (6 months of expenses). You have ${inr(plan.emergency.current)}.`}>
          {plan.emergency.fund ? (
            <FundLine
              f={plan.emergency.fund}
              monthly={plan.emergency.monthly}
              note={plan.emergency.months_to_complete ? `At this pace it's complete in about ${plan.emergency.months_to_complete} months. A liquid fund can be withdrawn within a day.` : undefined}
            />
          ) : (
            <p className="text-sm text-muted">Liquid fund scores aren&apos;t ready yet.</p>
          )}
          <div className="mt-3 flex flex-wrap items-start gap-3">
            {plan.emergency.fund && <GrowwButton fundName={plan.emergency.fund.name} />}
            <div className="min-w-0 flex-1">
              <Steps steps={plan.emergency.groww_steps} />
            </div>
          </div>
        </Card>
      )}

      {plan.sips.length > 0 && (
        <Card title={`${plan.emergency ? "Step 2 · " : ""}Your SIPs — one per fund`} subtitle="What you'd set up on Groww. Several goals can share a fund; the amounts are added up.">
          <div className="grid gap-4">
            {plan.sips.map((s) => (
              <div key={s.fund.scheme_code} className="rounded-xl border border-border bg-surface p-4 shadow-xs">
                <FundLine f={s.fund} note={`${s.label} · for ${s.goals.join(", ")}`} />
                <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  <span>
                    Start with <b className="num">{inr(s.monthly_affordable)}/mo</b>
                    {s.monthly_affordable === 0 && <span className="text-muted"> (after the emergency fund is built)</span>}
                  </span>
                  <span className="text-muted">Plan needs {inr(s.monthly_needed)}/mo</span>
                </div>
                <div className="mt-3 flex flex-wrap items-start gap-3">
                  <GrowwButton fundName={s.fund.name} label={s.monthly_affordable > 0 ? "Start SIP on Groww" : "View on Groww"} variant={s.monthly_affordable > 0 ? "primary" : "secondary"} />
                  <div className="min-w-0 flex-1">
                    <Steps steps={s.groww_steps} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {plan.goals.length === 0 ? (
        <Card title="No goals yet">
          <p className="text-sm text-muted">
            Add a goal on <Link href="/profile" className="font-semibold text-brand-strong hover:underline">My profile</Link> to get a SIP plan for it.
          </p>
        </Card>
      ) : (
        plan.goals.map((g) => <GoalCard key={g.id} g={g} />)
      )}

      <SipCalculator mix={longGoal?.allocation ?? { nifty_50_index: 100 }} />

      <Card title="Assumptions" subtitle="Yearly returns before tax used for planning — judgement calls, not predictions. Change them in backend/app/rules/plan.yaml.">
        <div className="overflow-x-auto">
          <table className="nm-table min-w-[420px]">
            <thead>
              <tr>
                <th>Fund type</th>
                <th className="text-right">Cautious</th>
                <th className="text-right">Normal</th>
                <th className="text-right">Good</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(plan.assumptions).map(([k, [c, e, o]]) => (
                <tr key={k}>
                  <td className="capitalize">{k.replace(/_/g, " ")}</td>
                  <td className="num text-right">{pct(c)}</td>
                  <td className="num text-right font-medium">{pct(e)}</td>
                  <td className="num text-right">{pct(o)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <p className="text-xs leading-relaxed text-muted">{DISCLAIMER}</p>
    </div>
  );
}

export default function Page() {
  return (
    <AppShell>
      <PlanPage />
    </AppShell>
  );
}
