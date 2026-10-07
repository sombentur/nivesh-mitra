import { AllocationBar } from "@/components/AllocationBar";
import { Badge, Card, Notice } from "@/components/ui";
import type { Category, Emergency, ProfileView } from "@/lib/api";
import { inr, titleCase } from "@/lib/format";

const CATEGORY_TEXT: Record<Category, string> = {
  conservative: "Protecting what you have comes first. Mostly steady funds, very little in shares of single companies.",
  moderate: "A balance of growth and safety. Mostly mutual funds, some long-term stocks, a tiny trading slice.",
  aggressive: "Comfortable with bigger ups and downs for more growth over the long run. Mutual funds still form the base.",
};

export function CategoryHero({ category }: { category: Category }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">Your risk profile</p>
      <p className="mt-1 font-display text-4xl font-semibold tracking-tight text-brand">{titleCase(category)}</p>
      <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">{CATEGORY_TEXT[category]}</p>
    </div>
  );
}

export function EmergencyMeter({ e, targetMonths, showAction = true }: { e: Emergency; targetMonths: number; showAction?: boolean }) {
  const filled = Math.min(100, (e.current / Math.max(e.target, 1)) * 100);
  return (
    <div className="grid gap-2">
      <div className="flex items-baseline justify-between text-sm">
        <span>
          <b className="num">{e.months_covered}</b> of {targetMonths} months saved
        </span>
        <span className="num text-muted">
          {inr(e.current)} / {inr(e.target)}
        </span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-surface-3" role="meter" aria-valuenow={Math.round(filled)} aria-valuemin={0} aria-valuemax={100} aria-label="Emergency fund progress">
        <div className="h-full rounded-full bg-gradient-to-r from-[var(--series-1)] to-brand transition-[width] duration-700" style={{ width: `${filled}%` }} />
      </div>
      {!e.first_action ? (
        <Badge tone="good">✓ Emergency fund complete</Badge>
      ) : (
        showAction && <Notice tone="warn">{e.first_action}</Notice>
      )}
    </div>
  );
}

export function ProfileResultCards({ view, targetMonths }: { view: ProfileView; targetMonths: number }) {
  const r = view.result;
  const a = view.allocation;
  return (
    <div className="grid gap-6">
      <Card>
        <CategoryHero category={r.final_category} />
        <div className="mt-6 grid gap-2 border-t border-border pt-5 text-sm">
          <p className="font-display text-[15px] font-semibold">How we got there</p>
          <ul className="grid divide-y divide-border">
            {r.reasons.map((x) => (
              <li key={x.factor} className="flex flex-wrap gap-x-3 gap-y-0.5 py-2.5">
                <span className="w-32 shrink-0 text-muted">{x.factor}</span>
                <span className="min-w-[12rem] flex-1">{x.text}</span>
                {x.points !== null && <span className="num shrink-0 font-medium text-muted">{x.points}/4</span>}
              </li>
            ))}
          </ul>
          <p className="mt-2 leading-relaxed text-muted">
            What you can afford: <b className="text-text">{titleCase(r.capacity_category)}</b> ({r.capacity_score}/16 points). What
            you&apos;re comfortable with: <b className="text-text">{titleCase(r.tolerance_category)}</b>. Nivesh Mitra uses the more
            careful of the two.
          </p>
          {r.overrides.map((o) => (
            <Notice key={o} tone="warn">
              {o}
            </Notice>
          ))}
          {r.sanity_warnings.map((w) => (
            <Notice key={w} tone="warn">
              {w}
            </Notice>
          ))}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="How to split your investing" subtitle="Suggested for your profile. You can change it later on the My profile page.">
          <AllocationBar
            split={a.effective}
            caption={
              a.trading_locked
                ? `Your trading share (${a.target.trading}%) stays in mutual funds until it unlocks.`
                : undefined
            }
          />
          {a.trading_locked && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">
              {a.trading_lock_reasons.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Emergency fund" subtitle={`${targetMonths} months of expenses, kept in a liquid fund, before anything risky.`}>
          <EmergencyMeter e={r.emergency} targetMonths={targetMonths} />
        </Card>
      </div>
    </div>
  );
}
