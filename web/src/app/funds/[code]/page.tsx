"use client";

import Link from "next/link";
import { GrowwButton } from "@/components/GrowwButton";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { FundScoreCard } from "@/components/FundScoreCard";
import { LineChart, type ChartRange } from "@/components/LineChart";
import { Badge, Button, Card, Notice, PageSkeleton, Spinner, StatTile } from "@/components/ui";
import { api, type FundDetail } from "@/lib/api";
import { fmtDate, navFmt, pctReturn, titleCase } from "@/lib/format";

const RANGES: ChartRange[] = [
  { key: "6m", label: "6M", days: 183 },
  { key: "1y", label: "1Y", days: 366 },
  { key: "3y", label: "3Y", days: 1096 },
  { key: "5y", label: "5Y", days: 1827 },
  { key: "all", label: "All", days: 0 },
];

function ReturnTile({ label, value, note }: { label: string; value: number | null; note?: string }) {
  return <StatTile label={label} value={pctReturn(value)} hint={note} tone={value === null ? undefined : value >= 0 ? "good" : "bad"} />;
}

function FundPage() {
  const { code } = useParams<{ code: string }>();
  const [fund, setFund] = useState<FundDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<FundDetail>(`/mf/schemes/${code}`).then(setFund, (e) => setError(e.message));
  }, [code]);



  async function download() {
    setBusy(true);
    try {
      setFund(await api.post<FundDetail>(`/mf/schemes/${code}/history`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <Notice tone="bad">{error}</Notice>;
  if (!fund || String(fund.scheme_code) !== code) return <PageSkeleton cards={3} label="Loading the fund" />;

  const r = fund.returns;
  return (
    <div className="grid gap-6">
      <div>
        <Link href="/funds" className="inline-flex items-center gap-1 rounded text-sm font-medium text-muted hover:text-brand-strong">
          ← Mutual funds
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
          <h1 className="min-w-0 max-w-3xl text-[26px] font-semibold leading-tight sm:text-[30px]">{fund.name}</h1>
          <GrowwButton fundName={fund.name} label={fund.plan === "direct" ? "Buy on Groww" : "Open on Groww"} size="md" />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <Badge>{fund.asset_class}</Badge>
          <Badge>{fund.category}</Badge>
          <Badge tone={fund.plan === "direct" ? "good" : "warn"}>{titleCase(fund.plan)} plan</Badge>
          <Badge>{fund.option_detail || titleCase(fund.option)}</Badge>
          {fund.amc && <span className="text-muted">{fund.amc}</span>}
        </div>
      </div>

      {fund.plan === "regular" && (
        <Notice tone="warn">
          This is a <b>Regular</b> plan. Regular plans pay a commission every year out of your returns; the same fund&apos;s{" "}
          <b>Direct</b> plan doesn&apos;t.
          {fund.twin && (
            <>
              {" "}
              <Link href={`/funds/${fund.twin.scheme_code}`} className="font-semibold underline underline-offset-2">
                See the Direct plan
              </Link>
              .
            </>
          )}
        </Notice>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <Card
          title="NAV history"
          subtitle={r.history_from ? `Daily NAV since ${fmtDate(r.history_from)} (${fund.history.points.toLocaleString("en-IN")} days)` : undefined}
        >
          {fund.history.status === "ready" ? (
            <LineChart
              data={fund.chart}
              valueLabel="NAV"
              format={(v) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: v < 100 ? 2 : 0 })}`}
              height={300}
              ranges={RANGES}
              defaultRange="5y"
            />
          ) : (
            <div className="grid gap-3">
              <p className="text-sm text-muted">
                {fund.history.status === "failed"
                  ? `The history download failed (${fund.history.error}). It will be retried automatically.`
                  : fund.tracked
                    ? "This fund's history is queued. It downloads automatically in the background."
                    : "History for this fund isn't downloaded yet (only Direct–Growth funds are pre-downloaded)."}
              </p>
              <div>
                <Button onClick={download} disabled={busy}>
                  {busy && <Spinner />}
                  {busy ? "Downloading…" : "Download history now"}
                </Button>
              </div>
            </div>
          )}
        </Card>

        <Card title="Latest">
          <div className="num text-4xl font-semibold tracking-tight">₹{navFmt(fund.latest_nav)}</div>
          <div className="mt-1 text-sm text-muted">{fund.latest_nav_date ? `NAV on ${fmtDate(fund.latest_nav_date)}` : "No NAV"}</div>
          <dl className="mt-5 grid gap-2.5 border-t border-border pt-4 text-sm">
            {fund.launch_date && (
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Launched</dt>
                <dd>{fmtDate(fund.launch_date)}</dd>
              </div>
            )}
            <div className="flex justify-between gap-3">
              <dt className="text-muted">AMFI code</dt>
              <dd className="num font-medium">{fund.scheme_code}</dd>
            </div>
            {fund.isin && (
              <div className="flex justify-between gap-3">
                <dt className="text-muted">ISIN</dt>
                <dd className="font-mono text-xs">{fund.isin}</dd>
              </div>
            )}
            {fund.twin && (
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{titleCase(fund.twin.plan)} plan</dt>
                <dd>
                  <Link href={`/funds/${fund.twin.scheme_code}`} className="num rounded font-semibold text-brand-strong hover:underline">
                    ₹{navFmt(fund.twin.latest_nav)} →
                  </Link>
                </dd>
              </div>
            )}
          </dl>
        </Card>
      </div>

      {fund.scoring ? (
        <FundScoreCard s={fund.scoring} />
      ) : (
        fund.plan === "direct" &&
        fund.option === "growth" && <Notice>This fund hasn&apos;t been scored yet. Scores are recalculated every Saturday.</Notice>
      )}

      <Card
        title="Returns"
        subtitle="Point-to-point, annualised for 3 years and longer. The score above uses rolling returns — every 3/5/7-year period — which is the fairer comparison."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <ReturnTile label="1 year" value={r["1y"]} />
          <ReturnTile label="3 years" value={r["3y"]} note="per year" />
          <ReturnTile label="5 years" value={r["5y"]} note="per year" />
          <ReturnTile label="10 years" value={r["10y"]} note="per year" />
          <ReturnTile label="Since start of data" value={r.since_start} note={r.history_from ? `from ${fmtDate(r.history_from)}` : undefined} />
        </div>
        <p className="mt-4 text-xs leading-relaxed text-muted">Past performance does not guarantee future returns.</p>
      </Card>
    </div>
  );
}

export default function Page() {
  return (
    <AppShell>
      <FundPage />
    </AppShell>
  );
}
