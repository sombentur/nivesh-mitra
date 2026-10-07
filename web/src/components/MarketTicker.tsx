"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { api, type TickerData, type TickerItem } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const price = (n: number) => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function Row({ items, hidden }: { items: TickerItem[]; hidden?: boolean }) {
  return (
    <ul className="flex shrink-0 items-center" aria-hidden={hidden || undefined}>
      {items.map((i, n) => {
        const up = i.change_pct >= 0;
        const firstStock = i.kind === "stock" && (n === 0 || items[n - 1].kind !== "stock");
        return (
          <li key={i.symbol} className="flex items-center gap-2 whitespace-nowrap border-r border-white/10 px-4 text-[13px]">
            {firstStock && (
              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.1em] text-ink-muted ring-1 ring-white/15">Stocks</span>
            )}
            <span className={i.kind === "index" ? "font-semibold tracking-wide text-white" : "font-medium text-ink-text"}>{i.label}</span>
            <span className="num text-ink-text">{price(i.last)}</span>
            <span className={`num font-semibold ${up ? "text-ink-up" : "text-ink-down"}`}>
              {up ? "▲" : "▼"} {Math.abs(i.change_pct * 100).toFixed(2)}%
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Tape({ tag, tagClass, items, seconds, note, className = "" }: { tag: ReactNode; tagClass: string; items: TickerItem[]; seconds: number; note?: string; className?: string }) {
  const style = { "--marquee-duration": `${seconds}s` } as CSSProperties;
  return (
    <div className={`relative flex h-9 items-stretch overflow-hidden ${className}`}>
      <div className={`flex w-[6.5rem] shrink-0 items-center gap-1.5 whitespace-nowrap px-3 text-[11px] font-extrabold uppercase tracking-[0.12em] sm:w-[9.5rem] ${tagClass}`} title={note}>
        {tag}
      </div>
      {/* people who ask for less motion get a tape they can scroll by hand instead (see globals.css) */}
      <div className="nm-tape no-scrollbar relative min-w-0 flex-1 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_24px,black_calc(100%-24px),transparent)]">
        {items.length > 0 && (
          <div className="nm-marquee flex h-full w-max items-center" style={style}>
            <Row items={items} />
            <Row items={items} hidden />
          </div>
        )}
      </div>
    </div>
  );
}

/** Two scrolling tapes across the top of every page, like a TV strip: NSE on top, BSE below. */
export function MarketTicker() {
  const [data, setData] = useState<TickerData | null>(null);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const load = () =>
      api.get<TickerData>("/market/ticker").then(
        (d) => {
          if (stopped) return;
          setData(d);
          timer = setTimeout(load, d.market_open ? 60_000 : 600_000);
        },
        () => {
          if (!stopped) timer = setTimeout(load, 120_000);
        },
      );
    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);

  // on a phone the tag is narrower, so the word "Close" is dropped and the date stays
  const when = data?.live ? (
    "Live"
  ) : data?.as_of ? (
    <>
      <span className="hidden sm:inline">Close </span>
      {new Date(data.as_of).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
    </>
  ) : (
    "…"
  );
  const note = data?.as_of ? (data.live ? "Live prices from Groww" : `Prices at the close of ${fmtDate(data.as_of)}`) : undefined;
  const liveDot = data?.live ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> : null;
  const nse = data?.nse ?? [];
  const bse = data?.bse ?? [];
  return (
    <div className="relative z-10 shrink-0 bg-ink text-ink-text shadow-[0_1px_0_0_var(--ink-line)]">
      <Tape
        tag={
          <>
            {liveDot}
            <span>NSE</span>
            <span className="font-semibold normal-case tracking-normal opacity-85">{when}</span>
          </>
        }
        tagClass="bg-[linear-gradient(100deg,#018a50,#01854d_45%,#016a3d)] text-white"
        items={nse}
        seconds={Math.max(60, nse.length * 3.5)}
        note={note}
      />
      <Tape
        tag={
          <>
            {liveDot}
            <span>BSE</span>
            <span className="font-semibold normal-case tracking-normal opacity-85">{when}</span>
          </>
        }
        tagClass="bg-[linear-gradient(100deg,#2869cf,#1d4f9f_60%,#173f80)] text-white"
        items={bse}
        seconds={Math.max(45, bse.length * 3.8)}
        note={note}
        className="border-t border-white/[0.07] bg-ink-3"
      />
    </div>
  );
}
