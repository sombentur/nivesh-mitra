"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ChangePill } from "@/components/dashboard/MarketWidgets";
import { asOfNote, UpDownBar } from "@/components/dashboard/SectorParts";
import { IconArrowRight } from "@/components/icons";
import { Delta, Notice, PageHeader, PageSkeleton } from "@/components/ui";
import { api, type SectorOverview } from "@/lib/api";
import { fmtDate } from "@/lib/format";

function SectorsPage() {
  const [data, setData] = useState<SectorOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<SectorOverview>("/market/sectors").then(setData, (e) => setError(e.message));
  }, []);

  if (error) return <Notice tone="bad">{error}</Notice>;
  if (!data) return <PageSkeleton cards={3} label="Loading sectors" />;

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Market"
        title="Sectors"
        description={`How each part of the market moved: NSE's sector index where there is one, and the ${data.tracked} most-traded NSE stocks grouped by their main business. ${asOfNote(data)}.`}
      >
        <p className="mt-2 text-xs text-muted">
          <Link href="/" className="font-semibold text-brand-strong hover:underline">
            ← Dashboard
          </Link>
        </p>
      </PageHeader>

      <ul className="nm-stagger grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.sectors.map((s) => (
          <li key={s.key}>
            <Link href={`/sectors/${s.key}`} className="lift group flex h-full flex-col rounded-2xl border border-border bg-surface p-5 shadow-card">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-lg font-semibold group-hover:text-brand-strong">{s.label}</h2>
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">{s.about}</p>
                </div>
                <IconArrowRight className="mt-1 shrink-0 text-subtle transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-brand" />
              </div>
              <div className="mt-4 flex flex-wrap items-end justify-between gap-2">
                {s.index ? (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">{s.index.name}</p>
                    <p className="num mt-0.5 flex items-center gap-2 text-xl font-semibold tracking-tight">
                      {s.index.last.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                      <ChangePill pct={s.index.change_pct} />
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">Average move today</p>
                    <p className="mt-0.5 text-xl font-semibold tracking-tight">{s.summary.avg_change_pct === null ? <span className="text-muted">—</span> : <Delta value={s.summary.avg_change_pct} />}</p>
                  </div>
                )}
                <p className="num text-right text-xs text-muted">
                  {s.summary.companies === 0 ? (
                    "no tracked companies"
                  ) : (
                    <>
                      <b className="text-text">{s.summary.companies}</b> {s.summary.companies === 1 ? "company" : "companies"}
                      <br />
                      <span className="text-up">▲ {s.summary.advancers}</span> · <span className="text-down">▼ {s.summary.decliners}</span>
                      {s.summary.unchanged > 0 && ` · ${s.summary.unchanged} flat`}
                    </>
                  )}
                </p>
              </div>
              {s.summary.companies > 0 && <UpDownBar s={s.summary} className="mt-3" />}
              {s.summary.best && s.summary.worst && s.summary.companies > 1 && (
                <p className="num mt-2 flex justify-between gap-2 text-[11px] text-muted">
                  <span>
                    Best <b className="font-semibold text-text">{s.summary.best.symbol}</b> <Delta value={s.summary.best.change_pct} />
                  </span>
                  <span>
                    Worst <b className="font-semibold text-text">{s.summary.worst.symbol}</b> <Delta value={s.summary.worst.change_pct} />
                  </span>
                </p>
              )}
            </Link>
          </li>
        ))}
      </ul>

      {data.unclassified.length > 0 && (
        <Notice>
          {data.unclassified.length} tracked {data.unclassified.length === 1 ? "company isn't" : "companies aren't"} classified yet, so they appear in no sector:{" "}
          <span className="num font-medium">{data.unclassified.join(", ")}</span>. Add them to <code className="rounded bg-surface px-1 py-0.5 font-mono text-xs ring-1 ring-inset ring-border">backend\app\rules\sectors.yaml</code>.
        </Notice>
      )}

      <p className="text-xs leading-relaxed text-muted">
        Companies are grouped by their main business, from Nivesh Mitra&apos;s own list (checked {fmtDate(data.checked)}); NSE&apos;s official member list for
        each index may differ a little. Only the {data.tracked} most-traded NSE stocks are tracked. This shows what already happened. It is not a buy
        signal.
      </p>
    </div>
  );
}

export default function Page() {
  return (
    <AppShell>
      <SectorsPage />
    </AppShell>
  );
}
