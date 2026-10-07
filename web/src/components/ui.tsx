import Link from "next/link";
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import { IconArrowRight } from "@/components/icons";

/** The one card used across the app. `tone="glass"` is the frosted version for panels that float over a background. */
export function Card({ title, subtitle, action, children, className = "", bodyClassName = "", tone = "solid" }: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  tone?: "solid" | "glass";
}) {
  const head = title || subtitle || action;
  return (
    <section className={`flex flex-col rounded-2xl border border-border p-5 sm:p-6 ${tone === "glass" ? "glass" : "bg-surface shadow-card"} ${className}`}>
      {head && (
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            {title && <h2 className="text-base font-semibold leading-snug">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm leading-relaxed text-muted">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0 text-sm">{action}</div>}
        </div>
      )}
      <div className={`flex-1 ${head ? "mt-4" : ""} ${bodyClassName}`}>{children}</div>
    </section>
  );
}

/** Title block at the top of every page. */
export function PageHeader({ eyebrow, title, description, actions, children }: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0">
        <span className="mb-3 block h-1 w-10 rounded-full bg-gradient-to-r from-[var(--series-1)] to-brand" aria-hidden="true" />
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 className={`text-[26px] font-semibold leading-tight sm:text-[30px] ${eyebrow ? "mt-1" : ""}`}>{title}</h1>
        {description && <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** "Open →" style link for the corner of a card. */
export function LinkMore({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="group inline-flex items-center gap-1 rounded-md text-sm font-semibold text-brand-strong hover:text-brand">
      {children} <IconArrowRight width={14} height={14} className="transition-transform duration-200 group-hover:translate-x-0.5" />
    </Link>
  );
}

/** Small uppercase label above a section of the page. */
export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">{children}</p>;
}

/** A labelled number: "Typical 1-year return  6.8%". */
export function Stat({ label, value, hint, tone }: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: "good" | "bad" | "warn" }) {
  const color = tone === "good" ? "text-up" : tone === "bad" ? "text-down" : tone === "warn" ? "text-warn" : "";
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted">{label}</p>
      <p className={`num mt-0.5 text-[15px] font-semibold ${color}`}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] leading-snug text-muted">{hint}</p>}
    </div>
  );
}

/** The same, boxed: one figure in a row of figures ("Recommended SIP  ₹8,000/mo"). */
export function StatTile({ label, value, hint, tone, size = "lg", className = "" }: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "good" | "bad" | "warn";
  size?: "md" | "lg";
  className?: string;
}) {
  const color = tone === "good" ? "text-up" : tone === "bad" ? "text-down" : tone === "warn" ? "text-warn" : "";
  return (
    <div className={`min-w-0 rounded-xl bg-surface-2 p-3.5 ring-1 ring-inset ring-border ${className}`}>
      <div className="text-xs text-muted">{label}</div>
      <div className={`num mt-1 font-semibold tracking-tight ${size === "lg" ? "text-xl" : "text-[15px]"} ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] leading-snug text-muted">{hint}</div>}
    </div>
  );
}

/** Pill-style segmented control (tabs). */
export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="no-scrollbar -mx-1 flex gap-1 overflow-x-auto px-1 py-0.5">
      <div className="flex gap-1 rounded-xl bg-surface-2 p-1 ring-1 ring-inset ring-border">
        {options.map((o) => (
          <button
            key={o.value}
            role="tab"
            type="button"
            aria-selected={o.value === value}
            onClick={() => onChange(o.value)}
            className={`shrink-0 whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm ${
              o.value === value ? "bg-surface font-semibold text-text shadow-xs ring-1 ring-border dark:bg-surface-3" : "font-medium text-muted hover:text-text"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** 0–100 score as a small ring. */
export function ScoreRing({ score, size = 44 }: { score: number | null; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const v = score ?? 0;
  const color = v >= 70 ? "var(--brand)" : v >= 50 ? "var(--chart-line)" : "var(--warn)";
  return (
    <span className="relative inline-grid shrink-0 place-items-center" style={{ width: size, height: size }} title={`Score ${score ?? "—"} out of 100`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={4} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={`${(v / 100) * c} ${c}`}
        />
      </svg>
      <span className="num absolute text-[13px] font-semibold">{score === null ? "—" : Math.round(score)}</span>
    </span>
  );
}

export type ButtonVariant = "primary" | "navy" | "secondary" | "ghost" | "danger" | "danger-solid";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-xl font-semibold active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0";
const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-brand text-on-brand shadow-[inset_0_1px_0_rgb(255_255_255/0.18),0_8px_18px_-10px_var(--brand)] hover:bg-brand-strong",
  navy: "bg-navy text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.12),0_8px_18px_-10px_var(--navy)] hover:brightness-125",
  secondary: "border border-border-strong/70 bg-surface text-text shadow-xs hover:border-border-strong hover:bg-surface-2",
  ghost: "text-muted hover:bg-surface-2 hover:text-text",
  danger: "border border-bad/30 bg-surface text-bad shadow-xs hover:bg-bad-soft",
  "danger-solid": "bg-bad text-on-bad shadow-[inset_0_1px_0_rgb(255_255_255/0.18)] hover:brightness-110",
};
const BUTTON_SIZE = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2.5 text-sm" };

/** Class string for things that should look like a button but aren't one (links). */
export function buttonClass(variant: ButtonVariant = "primary", size: keyof typeof BUTTON_SIZE = "md") {
  return `${BUTTON_BASE} ${BUTTON_VARIANT[variant]} ${BUTTON_SIZE[size]}`;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: keyof typeof BUTTON_SIZE };

export function Button({ variant = "primary", size = "md", className = "", ...props }: ButtonProps) {
  return <button className={`${buttonClass(variant, size)} ${className}`} {...props} />;
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium">{label}</span>
      {hint && <span className="mt-0.5 block text-xs leading-relaxed text-muted">{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

export const inputClass =
  "w-full rounded-xl border border-border-strong/70 bg-surface px-3.5 py-2.5 text-sm text-text shadow-xs outline-none placeholder:text-subtle hover:border-border-strong focus:border-brand focus:ring-4 focus:ring-brand/15 disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted";

export type BadgeTone = "neutral" | "good" | "warn" | "bad" | "brand" | "gold" | "info";

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  const styles = {
    neutral: "bg-surface-2 text-muted ring-border",
    good: "bg-good-soft text-good ring-good/20",
    warn: "bg-warn-soft text-warn ring-warn/25",
    bad: "bg-bad-soft text-bad ring-bad/20",
    brand: "bg-brand-soft text-brand-strong ring-brand/25",
    gold: "bg-gold-soft text-gold ring-gold/25",
    info: "bg-info-soft text-info ring-info/20",
  }[tone];
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${styles}`}>{children}</span>;
}

const NOTICE_ICON = {
  neutral: <path d="M12 11v5m0-8.5v.5" />,
  good: <path d="m8 12.5 3 3 5-6" />,
  warn: <path d="M12 8v5m0 3v.5" />,
  bad: <path d="m9 9 6 6m0-6-6 6" />,
};

/** A message box. The icon says the same thing as the colour, so nobody has to rely on colour alone. */
export function Notice({ tone = "neutral", children }: { tone?: "neutral" | "good" | "warn" | "bad"; children: ReactNode }) {
  const styles = {
    neutral: "border-border bg-surface-2 [--tone:var(--info)]",
    good: "border-good/30 bg-good-soft [--tone:var(--good)]",
    warn: "border-warn/30 bg-warn-soft [--tone:var(--warn)]",
    bad: "border-bad/30 bg-bad-soft [--tone:var(--bad)]",
  }[tone];
  return (
    <div role={tone === "bad" ? "alert" : undefined} className={`flex gap-3 rounded-xl border px-4 py-3 text-sm leading-relaxed ${styles}`}>
      <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="var(--tone)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        {NOTICE_ICON[tone]}
      </svg>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** A quiet block that stands in for content while it loads. Size it with classes: `<Skeleton className="h-4 w-32" />`. */
export function Skeleton({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <span className={`skeleton block ${className}`} style={style} aria-hidden="true" />;
}

/** A few placeholder lines, with a hidden label for screen readers. */
export function SkeletonLines({ lines = 3, label = "Loading", className = "" }: { lines?: number; label?: string; className?: string }) {
  return (
    <div role="status" className={`grid gap-2.5 ${className}`}>
      <span className="sr-only">{label}…</span>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className="h-3.5" style={{ width: `${[92, 78, 64, 85, 55][i % 5]}%` }} />
      ))}
    </div>
  );
}

/** Whole-page placeholder: a title and a few cards, shown while a page reads its data. */
export function PageSkeleton({ cards = 2, label = "Loading" }: { cards?: number; label?: string }) {
  return (
    <div role="status" className="grid gap-6">
      <span className="sr-only">{label}…</span>
      <div className="grid gap-3">
        <Skeleton className="h-1 w-10 rounded-full" />
        <Skeleton className="h-8 w-56 max-w-full" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      {Array.from({ length: cards }, (_, i) => (
        <div key={i} className="grid gap-3 rounded-2xl border border-border bg-surface p-5 shadow-card sm:p-6">
          <Skeleton className="h-5 w-44" />
          <Skeleton className="h-3.5 w-[88%]" />
          <Skeleton className="h-3.5 w-[72%]" />
          <Skeleton className="h-24 w-full" />
        </div>
      ))}
    </div>
  );
}

/** Small spinning ring for buttons and inline "working" states. */
export function Spinner({ size = 16, className = "" }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" className={`animate-spin ${className}`} aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth={3} opacity={0.2} />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth={3} strokeLinecap="round" />
    </svg>
  );
}

/** ▲ 1.24% in green or ▼ 0.42% in red: the arrow and sign carry the meaning, the colour repeats it. */
export function Delta({ value, digits = 2, className = "" }: { value: number | null | undefined; digits?: number; className?: string }) {
  if (value === null || value === undefined) return <span className={`num text-muted ${className}`}>—</span>;
  const up = value >= 0;
  return (
    <span className={`num whitespace-nowrap font-semibold ${up ? "text-up" : "text-down"} ${className}`}>
      {up ? "▲" : "▼"} {Math.abs(value * 100).toFixed(digits)}%
    </span>
  );
}

export const DISCLAIMER =
  "Investments are subject to market risks. Past performance does not guarantee future returns. Final decisions are yours.";
