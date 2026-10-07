"use client";

import { inputClass } from "@/components/ui";
import { inr } from "@/lib/format";
import type { Option } from "@/lib/api";

const LABEL = "text-sm font-medium";
const HINT = "mt-0.5 block text-xs leading-relaxed text-muted";

export function MoneyInput({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="block">
      <span className={LABEL}>{label}</span>
      {hint && <span className={HINT}>{hint}</span>}
      <div className="relative mt-1.5">
        <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sm font-medium text-muted">₹</span>
        <input
          className={`${inputClass} num pl-8`}
          inputMode="numeric"
          value={value ?? ""}
          onChange={(e) => {
            const digits = e.target.value.replace(/\D/g, "");
            onChange(digits === "" ? null : Number(digits));
          }}
          placeholder="0"
        />
      </div>
      {value !== null && value >= 1000 && <span className="num mt-1 block text-xs font-medium text-brand-strong">{inr(value)}</span>}
    </label>
  );
}

export function NumberInput({
  label,
  hint,
  value,
  onChange,
  min,
  max,
}: {
  label: string;
  hint?: string;
  value: number | null;
  onChange: (v: number | null) => void;
  min?: number;
  max?: number;
}) {
  return (
    <label className="block">
      <span className={LABEL}>{label}</span>
      {hint && <span className={HINT}>{hint}</span>}
      <input
        className={`${inputClass} num mt-1.5`}
        inputMode="numeric"
        value={value ?? ""}
        min={min}
        max={max}
        onChange={(e) => {
          const digits = e.target.value.replace(/\D/g, "");
          onChange(digits === "" ? null : Number(digits));
        }}
      />
    </label>
  );
}

export function RadioCards({
  label,
  hint,
  options,
  value,
  onChange,
  columns = 2,
}: {
  label: string;
  hint?: string;
  options: Option[];
  value: string | null;
  onChange: (v: string) => void;
  columns?: 2 | 3;
}) {
  return (
    <fieldset>
      <legend className={LABEL}>{label}</legend>
      {hint && <p className={HINT}>{hint}</p>}
      <div role="radiogroup" aria-label={label} className={`mt-2 grid gap-2 ${columns === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
        {options.map((o) => {
          const on = value === o.value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(o.value)}
              className={`flex items-start gap-3 rounded-xl border px-3.5 py-3 text-left text-sm ${
                on ? "border-brand bg-brand-soft font-medium shadow-[0_0_0_1px_var(--brand)]" : "border-border-strong/70 bg-surface shadow-xs hover:border-border-strong hover:bg-surface-2"
              }`}
            >
              <span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border-2 ${on ? "border-brand" : "border-border-strong"}`} aria-hidden="true">
                {on && <span className="h-2 w-2 rounded-full bg-brand" />}
              </span>
              <span className="min-w-0 flex-1">{o.label}</span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
