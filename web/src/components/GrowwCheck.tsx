"use client";

import { useState } from "react";
import { Badge, Button, Notice, Spinner } from "@/components/ui";
import { api, type GrowwCheck as Check, type GrowwCheckPart } from "@/lib/api";

const PARTS: [keyof Check, string][] = [
  ["login", "Log in"],
  ["portfolio", "Read your holdings"],
  ["prices", "Live prices"],
  ["history", "Price history (needed for trading ideas)"],
];

/** Runs a read-only check against Groww and shows exactly which permissions your key has. */
export function GrowwCheck() {
  const [result, setResult] = useState<Check | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.post<Check>("/trading/groww-check"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Check failed");
    } finally {
      setBusy(false);
    }
  }

  const dataMissing = result && result.login?.ok && (!result.prices?.ok || !result.history?.ok);
  return (
    <div className="grid gap-3">
      <div>
        <Button variant="secondary" onClick={run} disabled={busy}>
          {busy && <Spinner />}
          {busy ? "Checking Groww…" : "Test Groww connection"}
        </Button>
      </div>
      {error && <Notice tone="bad">{error}</Notice>}
      {result && (
        <ul className="nm-enter grid gap-2 rounded-xl bg-surface-2 p-3.5 text-sm ring-1 ring-inset ring-border">
          {PARTS.map(([key, label]) => {
            const part = result[key] as GrowwCheckPart;
            return (
              <li key={key} className="flex flex-wrap items-start gap-2">
                {part === null ? <Badge>not tried</Badge> : part.ok ? <Badge tone="good">✓ works</Badge> : <Badge tone="bad">✗ blocked</Badge>}
                <span className="font-medium">{label}</span>
                {part && <span className="w-full text-xs text-muted sm:w-auto">{part.detail}</span>}
              </li>
            );
          })}
        </ul>
      )}
      {dataMissing && (
        <Notice tone="warn">
          Your Groww key can log in but can&apos;t read market data. On groww.in → Profile → <b>Trading APIs</b>, check your plan: Groww&apos;s
          free trial excludes live prices and price history; the paid Trade API plan includes them.
        </Notice>
      )}
      {result?.auth_method === "secret" && (
        <Notice>
          You&apos;re using an <b>API key + secret</b>, which Groww asks you to <b>approve every day</b> on its website. For automatic
          evening updates, generate a <b>TOTP token</b> instead (groww.in/trade-api/api-keys → Generate TOTP token) and paste the token and
          the text under its QR code into the two Groww boxes above.
        </Notice>
      )}
    </div>
  );
}
