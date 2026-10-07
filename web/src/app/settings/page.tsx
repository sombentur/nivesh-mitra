"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { confirmDialog } from "@/components/ConfirmDialog";
import { DataHealthCard } from "@/components/DataHealth";
import { GrowwCheck } from "@/components/GrowwCheck";
import { TrendlyneCheck } from "@/components/TrendlyneCheck";
import { Badge, Button, Card, inputClass, Notice, PageHeader, SkeletonLines, Spinner } from "@/components/ui";
import { api, type SecretStatus, type Settings } from "@/lib/api";

function SecretRow({ s, onChange }: { s: SecretStatus; onChange: () => void }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.put(`/settings/secrets/${s.name}`, { value });
      setValue("");
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    const ok = await confirmDialog({
      title: `Remove your ${s.label}?`,
      body: "The saved value is deleted from this PC. Features that need it stop working until you paste it again.",
      confirmLabel: "Remove",
      tone: "danger",
    });
    if (!ok) return;
    await api.del(`/settings/secrets/${s.name}`);
    onChange();
  }

  return (
    <div className="grid gap-2 border-b border-border py-5 last:border-0 last:pb-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">{s.label}</span>
        {s.is_set ? <Badge tone="good">✓ Saved ••••{s.last4}</Badge> : <Badge>Not set</Badge>}
      </div>
      <p className="text-xs leading-relaxed text-muted">{s.help}</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="password"
          autoComplete="off"
          className={inputClass}
          placeholder={s.is_set ? "Paste a new value to replace it" : "Paste here"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <div className="flex gap-2">
          <Button onClick={save} disabled={busy || !value.trim()}>
            {busy && <Spinner />}
            Save
          </Button>
          {s.is_set && (
            <Button variant="danger" onClick={remove}>
              Remove
            </Button>
          )}
        </div>
      </div>
      {error && <Notice tone="bad">{error}</Notice>}
    </div>
  );
}

function Choice<T extends string>({
  value,
  options,
  onPick,
}: {
  value: T;
  options: { value: T; label: string; hint: ReactNode }[];
  onPick: (v: T) => void;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onPick(o.value)}
          aria-pressed={value === o.value}
          className={`flex items-start gap-3 rounded-xl border p-3.5 text-left ${
            value === o.value ? "border-brand bg-brand-soft shadow-[0_0_0_1px_var(--brand)]" : "border-border-strong/70 bg-surface shadow-xs hover:border-border-strong hover:bg-surface-2"
          }`}
        >
          <span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border-2 ${value === o.value ? "border-brand" : "border-border-strong"}`} aria-hidden="true">
            {value === o.value && <span className="h-2 w-2 rounded-full bg-brand" />}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-semibold">{o.label}</span>
            <span className="mt-1 block text-xs leading-relaxed text-muted">{o.hint}</span>
          </span>
        </button>
      ))}
    </div>
  );
}

function SettingsPage() {
  const [secrets, setSecrets] = useState<SecretStatus[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSecrets = () => api.get<SecretStatus[]>("/settings/secrets").then(setSecrets, (e) => setError(e.message));
  useEffect(() => {
    loadSecrets();
    api.get<Settings>("/settings").then(setSettings, (e) => setError(e.message));
  }, []);

  async function update(changes: Partial<Settings>) {
    try {
      setSettings(await api.patch<Settings>("/settings", changes));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    }
  }

  const claudeKeySet = secrets.find((s) => s.name === "anthropic_api_key")?.is_set;

  return (
    <div className="grid gap-6">
      <PageHeader title="Settings" description="Your connections, how explanations are worded, where data comes from and the language." />
      {error && <Notice tone="bad">{error}</Notice>}

      <Card
        title="Connections"
        subtitle="Keys are encrypted on this PC and never shown again (only the last 4 characters). Nivesh Mitra never asks for your Groww or Google password."
      >
        {secrets.length === 0 && !error && <SkeletonLines lines={6} label="Loading your connections" />}
        {secrets.map((s) => (
          <SecretRow key={s.name} s={s} onChange={loadSecrets} />
        ))}
        <div className="mt-5 border-t border-border pt-5">
          <p className="mb-2.5 font-display text-[15px] font-semibold">Check your Groww connection</p>
          <GrowwCheck />
        </div>
        <div className="mt-5 border-t border-border pt-5">
          <p className="mb-2.5 font-display text-[15px] font-semibold">Check your Trendlyne connection</p>
          <TrendlyneCheck />
        </div>
      </Card>

      {settings && (
        <>
          <Card title="Explanations" subtitle="Numbers and recommendations always come from the rule-based engine. This only changes the wording.">
            <Choice
              value={settings.explanation_mode}
              onPick={(v) => update({ explanation_mode: v })}
              options={[
                { value: "template", label: "Manual (templates)", hint: "Fixed plain-language sentences. Free, works offline." },
                {
                  value: "claude",
                  label: "Claude API",
                  hint: claudeKeySet
                    ? "Friendlier wording. Falls back to templates automatically if anything fails."
                    : "Add your Claude API key above first. Until then, templates are used.",
                },
              ]}
            />
            {settings.explanation_mode === "claude" && (
              <label className="mt-4 flex flex-wrap items-center gap-3 text-sm font-medium">
                Monthly spending cap (₹)
                <input
                  type="number"
                  min={0}
                  step={50}
                  className={`${inputClass} w-32`}
                  defaultValue={settings.claude_monthly_cap_inr}
                  onBlur={(e) => update({ claude_monthly_cap_inr: Number(e.target.value) })}
                />
              </label>
            )}
          </Card>

          <Card title="Company fundamentals" subtitle="Where 5+ years of company financials come from (doc 06).">
            <Choice
              value={settings.fundamentals_provider}
              onPick={(v) => update({ fundamentals_provider: v })}
              options={[
                { value: "manual", label: "Manual uploads", hint: "You upload files, e.g. Screener “Export to Excel”. Free." },
                { value: "eodhd", label: "EODHD", hint: "Automatic, licensed. Needs an EODHD key (subscribe at step 7)." },
              ]}
            />
            <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-border pt-4 text-sm">
              <label className="flex cursor-pointer items-center gap-2.5">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[var(--brand)]"
                  checked={settings.trendlyne_enabled}
                  onChange={(e) => update({ trendlyne_enabled: e.target.checked })}
                />
                Use Trendlyne MCP for red-flag checks (pledge, ASM/GSM, insider trades, announcements)
              </label>
              <select
                className={`${inputClass} w-auto`}
                value={settings.trendlyne_plan}
                onChange={(e) => update({ trendlyne_plan: e.target.value as Settings["trendlyne_plan"] })}
              >
                <option value="pro">Pro plan (2,000 calls/month)</option>
                <option value="max">Max plan (10,000 calls/month)</option>
              </select>
            </div>
          </Card>

          <DataHealthCard />

          <Card title="Language">
            <Choice
              value={settings.language}
              onPick={(v) => update({ language: v })}
              options={[
                { value: "en", label: "English", hint: "Simple English everywhere." },
                { value: "kn", label: "ಕನ್ನಡ (Kannada)", hint: "Arrives in Phase 2. English is shown until then." },
              ]}
            />
          </Card>
        </>
      )}
    </div>
  );
}

export default function Page() {
  return (
    <AppShell allowIncompleteOnboarding>
      <SettingsPage />
    </AppShell>
  );
}
