const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

/** ₹12,50,000 — Indian digit grouping. */
export const inr = (n: number) => INR.format(n);

export const pct = (n: number) => `${n}%`;

export const titleCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

/** 0.1234 → "12.3%"; null → "—". */
export const pctReturn = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;

export const navFmt = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

export const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/** "Thu, 1 Oct" */
export const fmtDay = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

/** 0.0123 → "+1.2%", -0.05 → "−5.0%" */
export const signedPct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(digits)}%`;

/** "Parag Parikh Flexi Cap Fund - Direct Plan - Growth" or "…Fund- Growth - Direct" → "Parag Parikh Flexi Cap Fund" */
export const shortFundName = (name: string) => name.split(/\s*-\s*(?=(?:direct|regular|growth)\b)/i)[0].trim();
