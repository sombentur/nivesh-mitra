"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { GoalsEditor } from "@/components/GoalsEditor";
import { MoneyInput, NumberInput, RadioCards } from "@/components/inputs";
import { ProfileResultCards } from "@/components/ProfileSummary";
import { Button, Card, Notice, Skeleton, SkeletonLines, Spinner } from "@/components/ui";
import {
  api,
  ApiError,
  type OnboardingStatus,
  type ProfileAnswers,
  type ProfileRules,
  type ProfileView,
} from "@/lib/api";

type Draft = { [K in keyof ProfileAnswers]: ProfileAnswers[K] | null };
const EMPTY: Draft = {
  age: null,
  income_range: null,
  monthly_expenses: null,
  monthly_investable: null,
  emergency_savings: null,
  monthly_emi: null,
  horizon: null,
  fall_reaction: null,
  experience: null,
};

const STEPS = ["Welcome", "About you", "Safety net", "Investing style", "Goals", "Your profile", "Reality check", "Paper trading"];

function StepFrame({ title, intro, children, footer }: { title: string; intro?: ReactNode; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="nm-enter grid gap-6">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight sm:text-[30px]">{title}</h1>
        {intro && <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">{intro}</p>}
      </div>
      {children}
      <div className="flex flex-wrap gap-2.5">{footer}</div>
    </div>
  );
}

function Onboarding() {
  const router = useRouter();
  const [rules, setRules] = useState<ProfileRules | null>(null);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [step, setStep] = useState(0);
  const [a, setA] = useState<Draft>(EMPTY);
  const [view, setView] = useState<ProfileView | null>(null);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [r, s] = await Promise.all([api.get<ProfileRules>("/profile/rules"), api.get<OnboardingStatus>("/onboarding/status")]);
        setRules(r);
        setStatus(s);
        if (s.profile_done) setA((await api.get<ProfileView>("/profile")).answers);
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) setError(e instanceof Error ? e.message : "Could not load");
      }
    })();
  }, []);

  if (!rules || !status)
    return (
      <div className="mx-auto grid max-w-3xl gap-6">
        {error ? (
          <Notice tone="bad">{error}</Notice>
        ) : (
          <>
            <Skeleton className="h-1.5 w-full rounded-full" />
            <Skeleton className="h-8 w-64" />
            <Card>
              <SkeletonLines lines={5} label="Loading your questions" />
            </Card>
          </>
        )}
      </div>
    );

  const rerun = status.complete;
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setA((prev) => ({ ...prev, [k]: v }));
  const q = rules.questions;
  const next = () => {
    setError(null);
    setStep((s) => s + 1);
  };
  const back = () => {
    setError(null);
    setStep((s) => s - 1);
  };

  async function submitProfile() {
    setBusy(true);
    setError(null);
    try {
      setView(await api.post<ProfileView>("/profile", a));
      next();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save your answers");
    } finally {
      setBusy(false);
    }
  }

  async function acknowledge() {
    setBusy(true);
    try {
      await api.post("/onboarding/sebi-ack");
      next();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true);
    try {
      await api.post("/onboarding/complete");
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not finish");
      setBusy(false);
    }
  }

  const ageOk = a.age !== null && a.age >= 18 && a.age <= 100;
  const step1Ok = ageOk && !!a.income_range && !!a.monthly_expenses && a.monthly_investable !== null;
  const step2Ok = a.emergency_savings !== null && a.monthly_emi !== null;
  const step3Ok = !!a.horizon && !!a.fall_reaction && !!a.experience;
  const lastStep = rerun ? 5 : STEPS.length - 1;

  const nextBtn = (ok: boolean, label = "Next") => (
    <Button onClick={next} disabled={!ok}>
      {label}
    </Button>
  );
  const backBtn = step > 0 && (
    <Button variant="secondary" onClick={back}>
      Back
    </Button>
  );

  let body: ReactNode;
  switch (step) {
    case 0:
      body = (
        <StepFrame
          title={rerun ? "Update your risk profile" : "Let's get to know you"}
          intro="About 10 short questions, around 3 minutes. Your answers stay on this PC. They decide how careful Nivesh Mitra is with your money."
          footer={nextBtn(true, "Start")}
        >
          <Card>
            <ol className="grid gap-4 text-sm leading-relaxed">
              {[
                "A few questions about your income, expenses and savings.",
                "How you feel about ups and downs. There are no right answers; honest ones work best.",
                "Your goals, like a house, a child's education or retirement.",
                "Your profile and a suggested way to split your money, with the reasons.",
              ].map((line, i) => (
                <li key={line} className="flex items-start gap-3.5">
                  <span className="num grid h-6 w-6 shrink-0 place-items-center rounded-full bg-navy text-[11px] font-semibold text-white">{i + 1}</span>
                  <span className="min-w-0 flex-1 pt-0.5">{line}</span>
                </li>
              ))}
            </ol>
          </Card>
        </StepFrame>
      );
      break;
    case 1:
      body = (
        <StepFrame title="About you" footer={<>{backBtn}{nextBtn(step1Ok)}</>}>
          <Card>
            <div className="grid gap-5">
              <NumberInput label="Your age" value={a.age} onChange={(v) => set("age", v)} min={18} max={100} />
              <RadioCards
                label="Monthly take-home pay (after tax)"
                options={q.income_ranges}
                value={a.income_range}
                onChange={(v) => set("income_range", v)}
                columns={3}
              />
              <div className="grid gap-5 sm:grid-cols-2">
                <MoneyInput
                  label="Monthly household expenses"
                  hint="Rent, food, bills, school fees — everything except EMIs."
                  value={a.monthly_expenses}
                  onChange={(v) => set("monthly_expenses", v)}
                />
                <MoneyInput
                  label="How much can you invest each month?"
                  hint="An amount you can keep investing even in a bad month."
                  value={a.monthly_investable}
                  onChange={(v) => set("monthly_investable", v)}
                />
              </div>
            </div>
          </Card>
        </StepFrame>
      );
      break;
    case 2:
      body = (
        <StepFrame
          title="Your safety net"
          intro="Before investing in anything risky, you need money set aside for emergencies, and room in your budget for loans."
          footer={<>{backBtn}{nextBtn(step2Ok)}</>}
        >
          <Card>
            <div className="grid gap-5 sm:grid-cols-2">
              <MoneyInput
                label="Savings you could use in an emergency"
                hint="Savings account, FDs, liquid funds. Enter 0 if none."
                value={a.emergency_savings}
                onChange={(v) => set("emergency_savings", v)}
              />
              <MoneyInput
                label="Total EMIs per month"
                hint="Home, car, personal loans, credit-card EMIs. Enter 0 if none."
                value={a.monthly_emi}
                onChange={(v) => set("monthly_emi", v)}
              />
            </div>
          </Card>
        </StepFrame>
      );
      break;
    case 3:
      body = (
        <StepFrame title="How you invest" footer={<>{backBtn}{nextBtn(step3Ok)}</>}>
          <Card>
            <div className="grid gap-6">
              <RadioCards
                label="When will you need most of this money?"
                options={q.horizons}
                value={a.horizon}
                onChange={(v) => set("horizon", v)}
              />
              <RadioCards
                label="Imagine your investments fall 20% in one month. ₹1,00,000 becomes ₹80,000. What would you do?"
                hint="This happens every few years, even to the best investments."
                options={q.fall_reactions}
                value={a.fall_reaction}
                onChange={(v) => set("fall_reaction", v)}
                columns={3}
              />
              <RadioCards
                label="Your investing experience"
                options={q.experience}
                value={a.experience}
                onChange={(v) => set("experience", v)}
              />
            </div>
          </Card>
        </StepFrame>
      );
      break;
    case 4:
      body = (
        <StepFrame
          title="Your goals"
          intro="What are you investing for? Add as many as you like, or skip and add them later. Enter amounts in today's money; inflation is added for you."
          footer={
            <>
              {backBtn}
              <Button onClick={submitProfile} disabled={busy}>
                {busy && <Spinner />}
                {busy ? "Working it out…" : "See my profile"}
              </Button>
            </>
          }
        >
          <Card>
            <GoalsEditor rules={rules} />
          </Card>
        </StepFrame>
      );
      break;
    case 5:
      body = view && (
        <StepFrame
          title="Your profile"
          intro="Here's what your answers mean. Go back and change anything that doesn't feel right."
          footer={
            <>
              {backBtn}
              {rerun ? (
                <Button onClick={() => router.replace("/profile")}>Done</Button>
              ) : (
                nextBtn(true, "Looks right — continue")
              )}
            </>
          }
        >
          <ProfileResultCards view={view} targetMonths={rules.emergency_fund.target_months} />
        </StepFrame>
      );
      break;
    case 6:
      body = (
        <StepFrame
          title="A reality check before we start"
          intro="Short-term trading looks easy, and it isn't. These are SEBI's own findings about individual traders in India."
          footer={
            <>
              {backBtn}
              <Button onClick={acknowledge} disabled={!ack || busy}>
                Continue
              </Button>
            </>
          }
        >
          <Card>
            <ul className="grid gap-3">
              {rules.sebi_reality_check.map((f) => (
                <li key={f.text} className="rounded-xl border-l-4 border-bad bg-bad-soft/60 px-4 py-3">
                  <p className="text-sm leading-relaxed">{f.text}</p>
                  <p className="mt-1 text-xs text-muted">
                    {f.source}, {new Date(f.date).toLocaleDateString("en-IN", { month: "long", year: "numeric" })}
                  </p>
                </li>
              ))}
            </ul>
            <p className="mt-5 text-sm leading-relaxed">
              That&apos;s why Nivesh Mitra <b>never suggests F&amp;O, intraday, margin or penny stocks</b>. Short-term ideas stay in a
              small, capped bucket, and they&apos;re paper-only for your first {rules.paper_trading_days} days.
            </p>
            <label className={`mt-5 flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 text-sm ${ack ? "border-brand bg-brand-soft/60" : "border-border-strong/70 bg-surface-2 hover:border-border-strong"}`}>
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[var(--brand)]" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              <span>I have read this and understand that most individual traders lose money.</span>
            </label>
          </Card>
        </StepFrame>
      );
      break;
    case 7:
      body = (
        <StepFrame
          title={`Practice first: ${rules.paper_trading_days} days of paper trading`}
          intro="For your first two months, Nivesh Mitra follows its own advice with pretend money, so you can judge it before trusting it with yours."
          footer={
            <>
              {backBtn}
              <Button onClick={finish} disabled={busy}>
                {busy && <Spinner />}
                {busy ? "Starting…" : `Start my ${rules.paper_trading_days}-day practice period`}
              </Button>
            </>
          }
        >
          <Card>
            <ul className="grid gap-3.5 text-sm leading-relaxed [&>li]:relative [&>li]:pl-6 [&>li]:before:absolute [&>li]:before:left-0 [&>li]:before:top-[0.55em] [&>li]:before:h-1.5 [&>li]:before:w-1.5 [&>li]:before:rounded-full [&>li]:before:bg-brand">
              <li>A virtual <b>₹1,00,000</b> portfolio follows every recommendation, including all real costs.</li>
              <li>It&apos;s compared with the <b>Nifty 50</b> and a plain <b>Nifty 50 index fund</b>, so you see whether the advice is worth anything.</li>
              <li>Short-term trade ideas are <b>paper-only</b> during this period.</li>
              <li>Your SIPs and long-term plans can carry on with real money as usual. They&apos;ll carry a &quot;practice period&quot; banner.</li>
              <li>On day {rules.paper_trading_days} you get an honest report, and you decide whether to continue with real money.</li>
            </ul>
          </Card>
        </StepFrame>
      );
      break;
  }

  return (
    <div className="mx-auto grid max-w-3xl gap-6">
      <ol className="flex flex-wrap gap-1.5" aria-label="Progress">
        {STEPS.slice(0, lastStep + 1).map((s, i) => (
          <li
            key={s}
            className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${i < step ? "bg-brand" : i === step ? "bg-navy dark:bg-brand-strong" : "bg-surface-3"}`}
            title={s}
            aria-current={i === step ? "step" : undefined}
          />
        ))}
      </ol>
      <p className="-mt-3 text-xs font-medium text-muted">
        Step <span className="num">{step + 1}</span> of <span className="num">{lastStep + 1}</span> · <span className="text-text">{STEPS[step]}</span>
      </p>
      {body}
      {error && <Notice tone="bad">{error}</Notice>}
    </div>
  );
}

export default function Page() {
  return (
    <AppShell allowIncompleteOnboarding>
      <Onboarding />
    </AppShell>
  );
}
