"use client";

import { useState } from "react";
import { Badge, Button, Notice, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

type Result = { ok: boolean; detail: string; tools: { name: string; description: string }[]; sample: { ok: boolean; detail: string } | null };

/** Lists Trendlyne's tools (free); the sample lookup uses one call of your Trendlyne MCP plan. */
export function TrendlyneCheck() {
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(sample: boolean) {
    setBusy(true);
    try {
      setResult(await api.post<Result>(`/trading/trendlyne-check${sample ? "?sample=true" : ""}`));
    } catch (e) {
      setResult({ ok: false, detail: e instanceof Error ? e.message : "Check failed", tools: [], sample: null });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => run(false)} disabled={busy}>
          {busy && <Spinner />}
          {busy ? "Checking Trendlyne…" : "Test Trendlyne connection"}
        </Button>
        <Button variant="secondary" onClick={() => run(true)} disabled={busy}>
          …and fetch one sample (uses 1 call)
        </Button>
      </div>
      {result && (
        <div className="nm-enter grid gap-2 rounded-xl bg-surface-2 p-3.5 text-sm ring-1 ring-inset ring-border">
          <div className="flex flex-wrap items-center gap-2">
            {result.ok ? <Badge tone="good">✓ connected</Badge> : <Badge tone="bad">✗ problem</Badge>}
            <span>{result.detail}</span>
          </div>
          {result.sample && (
            <div className="flex flex-wrap items-center gap-2">
              {result.sample.ok ? <Badge tone="good">✓ data</Badge> : <Badge tone="bad">✗ data</Badge>}
              <span className="text-muted">{result.sample.detail}</span>
            </div>
          )}
          {result.tools.length > 0 && (
            <details className="text-xs text-muted">
              <summary className="w-fit rounded font-medium hover:text-text">Tools Trendlyne offers ({result.tools.length})</summary>
              <ul className="mt-2 grid gap-1.5 leading-relaxed">
                {result.tools.map((t) => (
                  <li key={t.name}>
                    <code className="rounded bg-surface px-1 py-0.5 font-mono text-[11px] text-text ring-1 ring-inset ring-border">{t.name}</code> — {t.description}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {!result.ok && result.detail.includes("Add your") && <Notice>Paste your Trendlyne MCP server URL in the box above first.</Notice>}
        </div>
      )}
    </div>
  );
}
