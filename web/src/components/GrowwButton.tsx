import { buttonClass } from "@/components/ui";
import { shortFundName } from "@/lib/format";

const EXTERNAL = (
  <svg viewBox="0 0 24 24" width={14} height={14} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 4h6v6" />
    <path d="M20 4 10 14" />
    <path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" />
  </svg>
);

/**
 * Groww's public search page (groww.in/search?q=…), checked 30 Sep 2026: a stock symbol lists that stock first; a fund name
 * works once generic words ("Fund", "Direct", "Growth"…) are dropped. Opening the link is all Nivesh Mitra does: you pick the
 * result, check it and place the order yourself on Groww.
 */
export function growwSearchUrl({ fundName, symbol }: { fundName?: string; symbol?: string }): string {
  const q = symbol
    ? symbol
    : shortFundName(fundName ?? "")
        .replace(/\b(fund|plan|direct|regular|growth|option|idcw)\b/gi, " ")
        .replace(/[()\-–]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
  return `https://groww.in/search?q=${encodeURIComponent(q)}`;
}

export function GrowwButton({
  fundName,
  symbol,
  label = "Buy on Groww",
  variant = "primary",
  size = "sm",
  className = "",
}: {
  fundName?: string;
  symbol?: string;
  label?: string;
  variant?: "primary" | "secondary";
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <a
      href={growwSearchUrl({ fundName, symbol })}
      target="_blank"
      rel="noopener noreferrer"
      title="Opens Groww in a new tab. You place the order yourself."
      className={`${buttonClass(variant, size)} shrink-0 gap-1.5 ${className}`}
    >
      {label} {EXTERNAL}
    </a>
  );
}
