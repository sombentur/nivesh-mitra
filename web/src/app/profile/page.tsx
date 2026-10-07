"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AllocationBar, BUCKETS } from "@/components/AllocationBar";
import { AppShell } from "@/components/AppShell";
import { GoalsEditor } from "@/components/GoalsEditor";
import { ProfileResultCards } from "@/components/ProfileSummary";
import { Badge, Button, buttonClass, Card, inputClass, Notice, PageHeader, PageSkeleton, Spinner } from "@/components/ui";
import { api, type ProfileRules, type ProfileView, type Split } from "@/lib/api";
import { fmtDate } from "@/lib/format";

function SplitEditor({ view, rules, onSaved }: { view: ProfileView; rules: ProfileRules; onSaved: (v: ProfileView) => void }) {
  const current = view.allocation.target;
  const [satellite, setSatellite] = useState(current.satellite);
  const [trading, setTrading] = useState(current.trading);
  const [reason, setReason] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const core = 100 - satellite - trading;
  const draft: Split = { core, satellite, trading };
  const changed = satellite !== current.satellite || trading !== current.trading;
  const raisingTrading = trading > current.trading;
  const lim = rules.limits;

  useEffect(() => {
    if (core < 0) return;
    const t = setTimeout(() => {
      api
        .post<{ ok: boolean; error: string | null; warnings: string[] }>("/profile/split-check", draft)
        .then((r) => {
          setWarnings(r.warnings);
          setError(r.error);
        })
        .catch(() => {});
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [satellite, trading]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const v = await api.put<ProfileView>("/profile/allocation", { ...draft, reason: raisingTrading ? reason : null });
      setReason("");
      onSaved(v);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setSatellite(view.allocation.default.satellite);
    setTrading(view.allocation.default.trading);
  }

  async function cancelPending() {
    onSaved(await api.del<ProfileView>("/profile/allocation/pending"));
  }

  const pending = view.allocation.pending;
  return (
    <Card
      title="Your split"
      subtitle={`Suggested for a ${view.result.final_category} investor: ${view.allocation.default.core} / ${view.allocation.default.satellite} / ${view.allocation.default.trading}. Mutual funds get whatever the other two don't use.`}
    >
      <div className="grid gap-5">
        <AllocationBar split={core >= 0 ? draft : current} />
        <label className="grid gap-1.5 text-sm">
          <span className="flex items-center justify-between">
            <span className="flex items-center gap-2 font-medium">
              <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: BUCKETS[1].color }} />
              {BUCKETS[1].label}
            </span>
            <b className="num rounded-md bg-surface-2 px-2 py-0.5 ring-1 ring-inset ring-border">{satellite}%</b>
          </span>
          <input type="range" className="h-2 w-full cursor-pointer accent-[var(--brand)]" min={0} max={60} value={satellite} onChange={(e) => setSatellite(Math.min(Number(e.target.value), 100 - trading))} />
          <span className="text-xs leading-relaxed text-muted">{BUCKETS[1].hint} Suggested up to {lim.satellite_warn_above}%.</span>
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="flex items-center justify-between">
            <span className="flex items-center gap-2 font-medium">
              <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: BUCKETS[2].color }} />
              {BUCKETS[2].label}
            </span>
            <b className="num rounded-md bg-surface-2 px-2 py-0.5 ring-1 ring-inset ring-border">{trading}%</b>
          </span>
          <input type="range" className="h-2 w-full cursor-pointer accent-[var(--brand)]" min={0} max={lim.trading_max} value={trading} onChange={(e) => setTrading(Math.min(Number(e.target.value), 100 - satellite))} />
          <span className="text-xs leading-relaxed text-muted">
            {BUCKETS[2].hint} Safe limit {lim.trading_warn_above}%, hard ceiling {lim.trading_max}%.
          </span>
        </label>

        {warnings.map((w) => (
          <Notice key={w} tone="warn">
            {w}
          </Notice>
        ))}

        {changed && raisingTrading && (
          <div className="grid gap-2">
            <Notice tone="warn">
              Raising your trading share is a <b>loosening</b> of your safety rules. It takes effect after{" "}
              {lim.loosen_delay_hours} hours, so it can&apos;t be done in the heat of the moment. Please say why.
            </Notice>
            <textarea
              className={inputClass}
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why do you want a bigger trading share? (at least 10 characters)"
            />
          </div>
        )}

        {error && <Notice tone="bad">{error}</Notice>}

        <div className="flex flex-wrap gap-2">
          <Button onClick={save} disabled={!changed || busy || core < 0 || (raisingTrading && reason.trim().length < 10)}>
            {busy && <Spinner />}
            {raisingTrading ? `Save (starts in ${lim.loosen_delay_hours} h)` : "Save split"}
          </Button>
          <Button variant="secondary" onClick={reset}>
            Back to suggested
          </Button>
        </div>

        {pending && (
          <Notice>
            <div className="flex flex-wrap items-center gap-3">
              <span>
                Waiting to take effect on <b>{new Date(pending.effective_at).toLocaleString("en-IN")}</b>:{" "}
                {pending.core} / {pending.satellite} / {pending.trading}.
                {pending.reason && <span className="text-muted"> Your reason: &ldquo;{pending.reason}&rdquo;</span>}
              </span>
              <Button variant="secondary" size="sm" onClick={cancelPending}>
                Cancel this change
              </Button>
            </div>
          </Notice>
        )}
      </div>
    </Card>
  );
}

function ProfilePage() {
  const [view, setView] = useState<ProfileView | null>(null);
  const [rules, setRules] = useState<ProfileRules | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.get<ProfileView>("/profile"), api.get<ProfileRules>("/profile/rules")]).then(
      ([v, r]) => {
        setView(v);
        setRules(r);
      },
      (e) => setError(e.message),
    );
  }, []);

  if (error) return <Notice tone="bad">{error}</Notice>;
  if (!view || !rules) return <PageSkeleton cards={3} label="Loading your profile" />;

  return (
    <div className="grid gap-6">
      <PageHeader
        title="My profile"
        description={`Set on ${fmtDate(view.created_at)} · review due ${fmtDate(view.review_due_on)} · rules v${view.rules_version}`}
        actions={
          <Link href="/onboarding" className={buttonClass("secondary")}>
            Retake the questionnaire
          </Link>
        }
      />
      {view.review_due && (
        <Notice tone="warn">It&apos;s been a year. Please retake the questionnaire, since your situation may have changed.</Notice>
      )}

      <ProfileResultCards view={view} targetMonths={rules.emergency_fund.target_months} />
      <SplitEditor key={`${view.id}-${JSON.stringify(view.allocation.target)}`} view={view} rules={rules} onSaved={setView} />

      <Card title="Goals" subtitle="Amounts are in today's money. The goal planner (step 4) will work out the SIP each goal needs.">
        <GoalsEditor rules={rules} />
      </Card>

      <Card title="Practice period">
        {view.paper.started_on ? (
          <p className="text-sm leading-relaxed">
            {view.paper.complete ? (
              <Badge tone="good">✓ Complete</Badge>
            ) : (
              <>
                <b className="num">{view.paper.days_left}</b> days left (ends {fmtDate(view.paper.ends_on!)}).
              </>
            )}{" "}
            Started {fmtDate(view.paper.started_on)}.
          </p>
        ) : (
          <p className="text-sm text-muted">Not started.</p>
        )}
      </Card>
    </div>
  );
}

export default function Page() {
  return (
    <AppShell>
      <ProfilePage />
    </AppShell>
  );
}
