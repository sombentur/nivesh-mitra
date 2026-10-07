"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Notice, SkeletonLines } from "@/components/ui";
import { api, type DataStatus } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";

export function useDataStatus(pollMs = 5000) {
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api.get<DataStatus>("/data/status").then(setStatus, (e) => setError(e.message)), []);
  const busy = status?.jobs.some((j) => j.running) ?? false;
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    const t = setInterval(load, busy ? pollMs : pollMs * 6); // poll faster while something is downloading
    return () => clearInterval(t);
  }, [load, busy, pollMs]);
  return { status, error, reload: load };
}

/** One line: how fresh the fund data is, and history-download progress. */
export function DataStrip({ status }: { status: DataStatus | null }) {
  if (!status) return null;
  const n = status.nav;
  const backfill = status.jobs.find((j) => j.name === "mf_history_backfill");
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
      {n.latest_nav_date ? (
        <span>
          NAVs as of <b className="text-text">{fmtDate(n.latest_nav_date)}</b> {n.fresh ? <Badge tone="good">fresh</Badge> : <Badge tone="warn">out of date</Badge>}
        </span>
      ) : (
        <span>No fund data yet — the first download starts automatically.</span>
      )}
      {n.tracked > 0 && (
        <span>
          History: <b className="num text-text">{n.synced.toLocaleString("en-IN")}</b> of {n.tracked.toLocaleString("en-IN")} funds
          {backfill?.running && backfill.progress ? ` · downloading (${backfill.progress.done}/${backfill.progress.total})` : ""}
        </span>
      )}
    </div>
  );
}

/** Jobs that only make sense after others finish. "Run now" waits while a prerequisite is still running. */
const DEPENDS: Record<string, string[]> = {
  stock_backfill: ["stock_universe"],
  stock_prices_daily: ["stock_universe"],
  stock_backtests: ["stock_universe", "stock_backfill"],
  trading_after_close: ["stock_universe", "stock_backfill", "stock_backtests", "stock_prices_daily"],
  mf_scoring: ["mf_history_backfill", "amfi_ter"],
};

export function DataHealthCard() {
  const { status, error, reload } = useDataStatus();
  const [msg, setMsg] = useState<string | null>(null);

  async function run(name: string) {
    const r = await api.post<{ started: boolean }>(`/data/jobs/${name}/run`);
    setMsg(r.started ? "Started — this list updates by itself." : "That job is already running.");
    setTimeout(reload, 800);
  }

  return (
    <Card
      title="Data"
      subtitle="Where your data comes from and when it last updated. Everything runs by itself, in the right order — you never need these buttons. They're only for when you want an update right now."
    >
      {error && <Notice tone="bad">{error}</Notice>}
      {!status && !error && <SkeletonLines lines={5} label="Loading data status" />}
      {status && (
        <div className="grid gap-4">
          <DataStrip status={status} />
          <ul className="grid gap-3">
            {status.jobs.map((j) => {
              const last = j.last_run;
              const waitingFor = (DEPENDS[j.name] ?? [])
                .map((d) => status.jobs.find((x) => x.name === d))
                .filter((x) => x?.running)
                .map((x) => x!.label);
              return (
                <li key={j.name} className="flex flex-wrap items-start gap-3 rounded-xl border border-border bg-surface p-3.5 text-sm shadow-xs">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 font-medium">
                      {j.label}
                      {j.running ? (
                        <Badge tone="warn">Running{j.progress ? ` ${j.progress.done}/${j.progress.total}` : "…"}</Badge>
                      ) : last?.status === "ok" ? (
                        <Badge tone="good">OK</Badge>
                      ) : last?.status === "failed" ? (
                        <Badge tone="bad">Failed</Badge>
                      ) : (
                        <Badge>Not run yet</Badge>
                      )}
                    </div>
                    {last && (
                      <p className="mt-1 text-xs leading-relaxed text-muted">
                        {fmtDateTime(last.started_at)} — {last.detail}
                      </p>
                    )}
                    {j.next_run_at && <p className="mt-0.5 text-xs text-muted">Next automatic run: {fmtDateTime(j.next_run_at)}</p>}
                    {waitingFor.length > 0 && !j.running && (
                      <p className="mt-0.5 text-xs text-warn">Waits for “{waitingFor.join("”, “")}” to finish — it will start by itself after that.</p>
                    )}
                  </div>
                  <Button variant="secondary" size="sm" onClick={() => run(j.name)} disabled={j.running || waitingFor.length > 0}>
                    Run now
                  </Button>
                </li>
              );
            })}
          </ul>
          {msg && <p className="text-xs text-muted">{msg}</p>}
        </div>
      )}
    </Card>
  );
}
