"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ChangePill } from "@/components/dashboard/MarketWidgets";
import { asOfNote, CompanyCards, CompanyTable, SectorChips, UpDownBar } from "@/components/dashboard/SectorParts";
import { LineChart, type ChartRange } from "@/components/LineChart";
import { Badge, Card, Delta, Notice, PageHeader, PageSkeleton, Stat } from "@/components/ui";
import { api, ApiError, type SectorDetail } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const RANGES: ChartRange[] = [
  { key: "1m", label: "1M", days: 31 },
  { key: "3m", label: "3M", days: 92 },
  { key: "6m", label: "6M", days: 183 },
  { key: "1y", label: "1Y", days: 0 },
];

function SectorPage() {
  const { key } = useParams<{ key: string }>();
  const [data, setData] = useState<SectorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<SectorDetail>(`/market/sectors/${key}`).then(setData, (e) => setError(e instanceof ApiError && e.status === 404 ? "There is no sector page with that name." : e.message));
  }, [key]);

  if (error)
    return (
      <div className="grid gap-4">
        <Notice tone="bad">{error}</Notice>
        <p className="text-sm">
          <Link href="/sectors" className="font-semibold text-brand-strong hover:underline">
            ← All sectors
          </Link>
        </p>
      </div>
    );
  if (!data || data.key !== key) return <PageSkeleton cards={2} label="Loading the sector" />;

  const i = data.index;
  const s = data.summary;
  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Sector"
        title={data.label}
        description={data.about}
        actions={
          i && (
            <div className="rounded-2xl border border-border bg-surface px-4 py-3 shadow-card">
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">{i.name}</p>
              <p className="num mt-0.5 flex items-center gap-2.5 text-2xl font-semibold tracking-tight">
                {i.last.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                <ChangePill pct={i.change_pct} />
              </p>
            </div>
          )
        }
      >
        <p className="mt-2 flex flex-wrap gap-x-3 text-xs text-muted">
          <Link href="/" className="font-semibold text-brand-strong hover:underline">
            ← Dashboard
          </Link>
          <Link href="/sectors" className="font-semibold text-brand-strong hover:underline">
            All sectors
          </Link>
          <span>{asOfNote(data)}</span>
        </p>
      </PageHeader>

      {i && (
        <Card title={`${i.name} index`} subtitle="Daily closes · information, not a forecast">
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="1 week" value={<Delta value={i.ret_1w} />} />
            <Stat label="1 month" value={<Delta value={i.ret_1m} />} />
            <Stat label="3 months" value={<Delta value={i.ret_3m} />} />
            <Stat label="From 52-week high" value={<Delta value={i.from_high} />} hint={`high ${i.high_52w.toLocaleString("en-IN", { maximumFractionDigits: 0 })} · low ${i.low_52w.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`} />
          </div>
          {data.history.length >= 2 ? (
            <LineChart data={data.history} valueLabel={i.name} format={(v) => v.toLocaleString("en-IN", { maximumFractionDigits: 0 })} height={260} ranges={RANGES} defaultRange="1y" />
          ) : (
            <p className="text-sm text-muted">The index history appears after the first price download.</p>
          )}
        </Card>
      )}

      <Card
        title={s.companies === 0 ? "Companies" : `${s.companies} tracked ${s.companies === 1 ? "company" : "companies"}`}
        subtitle={`Grouped by main business: ${data.industries.map((x) => x.label.toLowerCase()).join(" · ")}.`}
        action={
          s.companies > 0 && (
            <span className="num flex items-center gap-2 text-xs text-muted">
              <span className="font-semibold text-up">▲ {s.advancers}</span>
              <span className="font-semibold text-down">▼ {s.decliners}</span>
              {s.unchanged > 0 && <span>{s.unchanged} flat</span>}
              {s.avg_change_pct !== null && (
                <span>
                  · average <Delta value={s.avg_change_pct} />
                </span>
              )}
            </span>
          )
        }
      >
        {s.companies === 0 ? (
          <p className="rounded-xl border border-dashed border-border-strong p-6 text-center text-sm text-muted">
            None of the {data.tracked} most-traded NSE stocks is in this sector right now{i ? `, so only the ${i.name} index is shown` : ""}.
          </p>
        ) : (
          <div className="grid gap-6">
            <UpDownBar s={s} />
            {data.groups.map((g) => (
              <section key={g.industry} aria-label={g.label}>
                <h3 className="mb-2.5 flex items-center gap-2 text-[15px] font-semibold">
                  {g.label} <Badge>{g.companies.length}</Badge>
                </h3>
                <CompanyTable companies={g.companies} />
                <CompanyCards companies={g.companies} />
              </section>
            ))}
          </div>
        )}
        <p className="mt-5 border-t border-border pt-4 text-xs leading-relaxed text-muted">
          Companies are grouped by their main business, from Nivesh Mitra&apos;s own list (checked {fmtDate(data.checked)}).
          {i ? ` NSE's official member list for the ${i.name} index may differ a little.` : ""} Only the {data.tracked} most-traded NSE stocks are
          tracked. <b className="text-text">This shows what already happened. It is not a buy signal.</b> &quot;Chart&quot; opens Groww in a new tab;
          you place any order yourself.
        </p>
      </Card>

      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">Other sectors</p>
        <SectorChips items={data.others} />
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <AppShell>
      <SectorPage />
    </AppShell>
  );
}
