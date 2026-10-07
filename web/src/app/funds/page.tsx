"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { DataStrip, useDataStatus } from "@/components/DataHealth";
import { Card, inputClass, Notice, PageHeader, ScoreRing, SkeletonLines } from "@/components/ui";
import { api, type FundBrief, type FundCategory } from "@/lib/api";
import { fmtDate, navFmt } from "@/lib/format";

function FundsPage() {
  const { status } = useDataStatus();
  const [categories, setCategories] = useState<FundCategory[]>([]);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [includeAll, setIncludeAll] = useState(false);
  const [results, setResults] = useState<FundBrief[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<FundCategory[]>("/mf/categories").then(setCategories, (e) => setError(e.message));
  }, [status?.nav.latest_nav_date]);

  useEffect(() => {
    const t = setTimeout(() => {
      const params = new URLSearchParams({ q, limit: "100" });
      if (category) params.set("category", category);
      if (includeAll) params.set("include_all", "true");
      api.get<FundBrief[]>(`/mf/search?${params}`).then(setResults, (e) => setError(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [q, category, includeAll, status?.nav.latest_nav_date]);

  const grouped = useMemo(() => {
    const g: Record<string, FundCategory[]> = {};
    for (const c of categories) (g[c.asset_class] ??= []).push(c);
    return g;
  }, [categories]);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Mutual funds"
        description={
          <>
            Every active fund in India, from AMFI&apos;s official daily data. By default you see <b>Direct – Growth</b> plans only:
            they cost less than Regular plans and are the ones Nivesh Mitra compares. Pick a category to see its funds ranked by score.
          </>
        }
      >
        <div className="mt-3">
          <DataStrip status={status} />
        </div>
      </PageHeader>

      <Card>
        <div className="grid gap-3 sm:grid-cols-[1fr_280px]">
          <div className="relative">
            <svg viewBox="0 0 24 24" width={17} height={17} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-subtle" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input
              className={`${inputClass} pl-10`}
              type="search"
              aria-label="Search funds"
              placeholder="Search by fund or AMC name, e.g. parag flexi, nifty 50 index, hdfc"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              autoFocus
            />
          </div>
          <select className={inputClass} aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {Object.entries(grouped).map(([ac, cats]) => (
              <optgroup key={ac} label={ac}>
                {cats.map((c) => (
                  <option key={c.category} value={c.category}>
                    {c.category} ({c.count})
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
        <label className="mt-3.5 flex cursor-pointer items-center gap-2.5 text-xs text-muted">
          <input type="checkbox" className="h-4 w-4 accent-[var(--brand)]" checked={includeAll} onChange={(e) => setIncludeAll(e.target.checked)} />
          Also show Regular plans and IDCW options (useful for finding a fund you already own)
        </label>
      </Card>

      {error && <Notice tone="bad">{error}</Notice>}

      {!results && !error && (
        <Card>
          <SkeletonLines lines={6} label="Loading funds" />
        </Card>
      )}

      {results && (
        <Card title={`${results.length}${results.length === 100 ? "+" : ""} funds`}>
          {results.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border-strong p-6 text-center text-sm text-muted">
              {status?.nav.latest_nav_date ? "No funds match. Try fewer words." : "Fund data is still downloading. Check back in a minute."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="nm-table min-w-[640px]">
                <thead>
                  <tr>
                    <th>Fund</th>
                    <th>Category</th>
                    <th className="text-right">Score</th>
                    <th className="text-right">NAV (₹)</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((f) => (
                    <tr key={f.scheme_code}>
                      <td>
                        <Link href={`/funds/${f.scheme_code}`} className="rounded font-medium hover:text-brand-strong hover:underline">
                          {f.name}
                        </Link>
                        {f.amc && <div className="mt-0.5 text-xs text-muted">{f.amc}</div>}
                      </td>
                      <td className="text-muted">{f.category}</td>
                      <td className="num text-right">
                        {f.score?.total != null ? (
                          <span className="inline-flex items-center justify-end gap-2.5">
                            <span className="text-right text-xs text-muted">
                              #{f.score.rank} of {f.score.peers}
                              {f.score.confidence === "low" && <span className="block">low confidence</span>}
                            </span>
                            <ScoreRing score={f.score.total} size={38} />
                          </span>
                        ) : (
                          <span className="text-xs text-muted">—</span>
                        )}
                      </td>
                      <td className="num text-right font-medium">
                        {navFmt(f.latest_nav)}
                        {f.latest_nav_date && <div className="mt-0.5 text-xs font-normal text-muted">{fmtDate(f.latest_nav_date)}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

export default function Page() {
  return (
    <AppShell>
      <FundsPage />
    </AppShell>
  );
}
