"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Freshness } from "@/lib/api";

const day = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
};
const clock = (d: Date) => d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });

/**
 * One button for every page: brings prices and NAVs up to date if a finished session is missing, then reloads what is on
 * screen. It also watches for downloads that finish on their own (the 4:45 PM update) so the page never sits on old data.
 */
export function RefreshButton({ onReload }: { onReload: () => void }) {
  const pathname = usePathname();
  const [fresh, setFresh] = useState<Freshness | null>(null);
  const [starting, setStarting] = useState(false);
  const [loadedAt, setLoadedAt] = useState(() => new Date());
  const [newData, setNewData] = useState(false); // something finished downloading while this page was open
  const [done, setDone] = useState(false); // a short "up to date" confirmation after a refresh
  const wasRunning = useRef(false);
  const mine = useRef(false); // the download in progress was started by this button
  const busy = starting || (fresh?.running.length ?? 0) > 0;

  const reload = useCallback(() => {
    onReload();
    setLoadedAt(new Date());
    setNewData(false);
    setDone(true);
  }, [onReload]);

  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => setDone(false), 4000);
    return () => clearTimeout(t);
  }, [done]);

  const check = useCallback(
    () =>
      api.get<Freshness>("/data/freshness").then(
        (f) => {
          const running = f.running.length > 0;
          if (wasRunning.current && !running) {
            // a download just finished: show it at once on the dashboard or when you asked for it; elsewhere, offer it
            if (mine.current || pathname === "/") reload();
            else setNewData(true);
            mine.current = false;
          }
          wasRunning.current = running;
          setFresh(f);
        },
        () => {},
      ),
    [pathname, reload],
  );

  useEffect(() => {
    const first = setTimeout(check, 0);
    const t = setInterval(check, busy ? 4000 : 60000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [check, busy]);

  async function refresh() {
    if (busy) return;
    setStarting(true);
    try {
      const f = await api.post<Freshness>("/data/refresh");
      setFresh(f);
      if ((f.started?.length ?? 0) > 0) {
        mine.current = true;
        wasRunning.current = true;
      } else {
        reload(); // nothing to download: just read everything again
      }
    } catch {
      reload();
    } finally {
      setStarting(false);
    }
  }

  const job = fresh?.running[0];
  const p = fresh?.prices;
  let line = "";
  let tone = "text-ink-muted";
  if (busy) {
    line = job ? (job.progress ? `Updating ${job.progress.done}/${job.progress.total}` : "Updating…") : "Checking…";
    tone = "text-ink-accent";
  } else if (p?.error) {
    line = "Update failed · retry";
    tone = "text-ink-down";
  } else if (done) {
    line = "Up to date ✓";
    tone = "text-ink-accent";
  } else if (p?.behind || newData) {
    line = "New data · tap";
    tone = "text-ink-gold";
  } else if (fresh?.market_open) {
    line = `Live · ${clock(loadedAt)}`;
  } else if (p?.latest_session) {
    line = `To ${day(p.latest_session)}`;
  }
  const title = busy
    ? (job?.label ?? "Checking for new data")
    : p?.error
      ? `The last price update failed: ${p.error}`
      : `Prices are in up to ${p?.latest_session ? day(p.latest_session) : "—"}${fresh?.navs.date ? `; fund NAVs to ${day(fresh.navs.date)}` : ""}. This page was loaded at ${clock(loadedAt)}. Click to check for newer data and reload.`;

  return (
    <button
      type="button"
      onClick={refresh}
      title={title}
      aria-label="Refresh data"
      aria-busy={busy}
      className="group flex w-[5.5rem] shrink-0 flex-col items-center justify-center gap-0.5 border-l border-white/10 bg-ink px-2 text-ink-text shadow-[0_1px_0_0_var(--ink-line)] hover:bg-ink-2 focus-visible:-outline-offset-2 focus-visible:outline-ink-accent sm:w-32"
    >
      <span className="flex items-center gap-1.5 text-xs font-semibold">
        <svg
          viewBox="0 0 24 24"
          width={15}
          height={15}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className={busy ? "animate-spin text-ink-accent" : "text-ink-accent transition-transform duration-300 group-hover:rotate-45"}
        >
          <path d="M20 11a8 8 0 1 0-2.3 5.7" />
          <path d="M20 4v7h-7" />
        </svg>
        Refresh
      </span>
      <span className={`num max-w-full truncate text-[10px] leading-tight ${tone}`}>{line}</span>
    </button>
  );
}
