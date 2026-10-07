"use client";

import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";

const listeners = new Set<() => void>();
const read = (): Theme => (typeof document !== "undefined" && document.documentElement.dataset.theme === "dark" ? "dark" : "light");

function set(t: Theme) {
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem("nm-theme", t);
  } catch {
    // private window: the choice lasts until the page is closed
  }
  listeners.forEach((l) => l());
}

/** Light / dark switch for the sidebar. The saved choice is applied before the page paints (see app/layout.tsx). */
export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const theme = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    read,
    () => "light" as Theme,
  );
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => set(next)}
      title={`Switch to ${next} theme`}
      aria-label={`Switch to ${next} theme`}
      className={`flex items-center gap-3 rounded-xl font-medium text-muted hover:bg-surface-2 hover:text-text ${compact ? "p-2" : "w-full px-3 py-2.5 text-sm"}`}
    >
      {theme === "dark" ? (
        <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />
        </svg>
      )}
      {!compact && (theme === "dark" ? "Light theme" : "Dark theme")}
    </button>
  );
}
