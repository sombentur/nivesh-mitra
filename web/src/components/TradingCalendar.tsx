"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type CalendarData, type CalendarDay } from "@/lib/api";

type View = "month" | "week";

const VIEW_KEY = "nm-cal-view";
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// The sidebar is rebuilt on every page, so answers are kept here to show the calendar instantly while it refreshes.
const cache = new Map<string, CalendarData>();

// Calendar dates in local time. (toISOString() would shift the day: midnight in India is still yesterday in UTC.)
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (s: string) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const monday = (d: Date) => addDays(d, -((d.getDay() + 6) % 7));
const fmt = (s: string, o: Intl.DateTimeFormatOptions) => parse(s).toLocaleDateString("en-GB", o);
const pct = (v: number) => `${v >= 0 ? "▲" : "▼"} ${Math.abs(v * 100).toFixed(2)}%`;
const rupees = (v: number) => `${v >= 0 ? "+" : "−"}₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

function savedView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "week" ? "week" : "month";
  } catch {
    return "month";
  }
}

/** What the day is, in words: used for the detail line, tooltips and screen readers. */
function describe(d: CalendarDay, today: string): string {
  if (d.status === "holiday") return `Market holiday${d.name && d.name !== "Market holiday" ? ` · ${d.name}` : ""}`;
  if (d.status === "weekend") return d.name ? `Weekend · ${d.name}` : "Weekend · market closed";
  if (d.status === "special") return d.name ?? "Special trading session";
  if (d.nifty) return `Nifty 50 ${pct(d.nifty.change_pct)}`;
  return d.date < today ? "Trading day · prices not downloaded yet" : "Trading day · 9:15 AM – 3:30 PM";
}

function hasMark(d: CalendarDay) {
  return d.events.length > 0 || d.pnl !== null || d.ideas > 0;
}

/** Green for an up day, red for a down day; a bigger move gets a deeper tint. The tooltip gives the number. */
function tint(d: CalendarDay): string | undefined {
  if (!d.nifty) return undefined;
  const strength = Math.round(Math.min(0.14 + Math.abs(d.nifty.change_pct) * 14, 0.5) * 100);
  return `color-mix(in oklab, var(${d.nifty.change_pct >= 0 ? "--up" : "--down"}) ${strength}%, transparent)`;
}

function Extras({ d }: { d: CalendarDay }) {
  return (
    <>
      {d.sensex && <p className="num">Sensex {pct(d.sensex.change_pct)}</p>}
      {d.note && <p>{d.note}</p>}
      {d.pnl !== null && (
        <p>
          Practice: <b className={d.pnl >= 0 ? "text-up" : "text-down"}>{rupees(d.pnl)}</b> from {d.closed_trades} trade{d.closed_trades === 1 ? "" : "s"}
        </p>
      )}
      {d.ideas > 0 && (
        <p>
          {d.ideas} practice idea{d.ideas === 1 ? "" : "s"} for this session
        </p>
      )}
      {d.events.map((e) => (
        <p key={e} className="font-medium text-brand-strong">
          {e}
        </p>
      ))}
    </>
  );
}

function MonthGrid({ days, month, today, selected, onSelect }: { days: CalendarDay[]; month: number; today: string; selected: string; onSelect: (d: string) => void }) {
  // six weeks are fetched; a week with no day of this month isn't drawn
  const weeks = Array.from({ length: Math.ceil(days.length / 7) }, (_, i) => days.slice(i * 7, i * 7 + 7));
  const shown = weeks.filter((w) => w.some((d) => parse(d.date).getMonth() === month)).flat();
  return (
    <div className="grid grid-cols-7 gap-0.5" role="grid" aria-label="Month">
      {WEEKDAYS.map((w, i) => (
        <span key={w} className={`pb-1 text-center text-[10px] font-semibold ${i >= 5 ? "text-subtle" : "text-muted"}`}>
          {w[0]}
        </span>
      ))}
      {shown.map((d) => {
        const date = parse(d.date);
        const closed = d.status === "weekend" || d.status === "holiday";
        const special = d.status === "holiday" || d.status === "special";
        return (
          <button
            key={d.date}
            type="button"
            onClick={() => onSelect(d.date)}
            title={`${fmt(d.date, { weekday: "short", day: "numeric", month: "short" })}: ${describe(d, today)}`}
            aria-label={`${fmt(d.date, { weekday: "long", day: "numeric", month: "long" })}: ${describe(d, today)}`}
            aria-pressed={d.date === selected}
            className={`num relative grid h-7 place-items-center rounded-md text-[12px] hover:bg-surface-3 focus-visible:outline-offset-0 ${date.getMonth() !== month ? "opacity-35" : ""} ${
              special ? "text-gold" : closed ? "text-subtle" : "text-text"
            } ${d.date === today ? "font-bold" : ""}`}
            style={{
              background: tint(d) ?? (d.date === selected ? "var(--surface-3)" : undefined), // an up/down day keeps its colour when picked
              boxShadow: d.date === today ? "inset 0 0 0 1.5px var(--brand)" : d.date === selected ? "inset 0 0 0 1.5px var(--text)" : undefined,
            }}
          >
            {date.getDate()}
            {special && <span className="absolute bottom-[3px] h-[3px] w-[3px] rounded-full bg-gold" />}
            {hasMark(d) && <span className="absolute right-[3px] top-[3px] h-1 w-1 rounded-full bg-brand" />}
          </button>
        );
      })}
    </div>
  );
}

function WeekList({ days, today, selected, onSelect }: { days: CalendarDay[]; today: string; selected: string; onSelect: (d: string) => void }) {
  return (
    <ul className="grid gap-1">
      {days.map((d) => {
        const date = parse(d.date);
        const closed = d.status !== "trading";
        const more = d.sensex || d.note || d.pnl !== null || d.ideas > 0 || d.events.length > 0 || (closed && d.name);
        return (
          <li key={d.date}>
            <button
              type="button"
              onClick={() => onSelect(d.date)}
              aria-pressed={d.date === selected}
              className={`flex w-full items-start gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-surface-3 focus-visible:outline-offset-0 ${d.date === selected ? "bg-surface-3" : ""}`}
              style={{ boxShadow: d.date === today ? "inset 0 0 0 1.5px var(--brand)" : undefined }}
            >
              <span className="w-8 shrink-0 text-center leading-tight">
                <span className="block text-[10px] font-medium uppercase tracking-wide text-muted">{WEEKDAYS[(date.getDay() + 6) % 7]}</span>
                <span className={`num block text-sm text-text ${d.date === today ? "font-bold" : ""}`}>{date.getDate()}</span>
              </span>
              <span className="min-w-0 flex-1 text-[11px] leading-snug text-muted">
                {d.status === "trading" && d.nifty ? (
                  <span className="num flex items-baseline justify-between gap-2 text-xs">
                    <b className={d.nifty.change_pct >= 0 ? "text-up" : "text-down"}>{pct(d.nifty.change_pct)}</b>
                    <span>{d.nifty.close.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
                  </span>
                ) : (
                  <span className={`block text-xs ${d.status === "holiday" || d.status === "special" ? "font-medium text-gold" : ""}`}>
                    {d.status === "holiday" ? "Holiday" : d.status === "weekend" ? "Weekend" : d.status === "special" ? "Special session" : d.date < today ? "Awaiting prices" : "Open 9:15 – 3:30"}
                  </span>
                )}
                {more && (
                  <span className="mt-0.5 block">
                    {closed && d.name && d.name !== "Market holiday" && <span className="block">{d.name}</span>}
                    <Extras d={d} />
                  </span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Market calendar for the sidebar: a month grid or a week list — open days, holidays, the Nifty's move and your own dates. */
export function TradingCalendar({ className = "" }: { className?: string }) {
  const [view, setView] = useState<View>(savedView);
  const [anchor, setAnchor] = useState(() => iso(new Date())); // any day inside the month or week on show
  const [selected, setSelected] = useState(() => iso(new Date()));
  const [loaded, setLoaded] = useState<{ key: string; data: CalendarData } | null>(null);
  const [tick, setTick] = useState(0);

  const range = useMemo(() => {
    const a = parse(anchor);
    const start = view === "week" ? monday(a) : monday(new Date(a.getFullYear(), a.getMonth(), 1));
    return { start: iso(start), end: iso(addDays(start, view === "week" ? 6 : 41)) };
  }, [anchor, view]);
  const key = `${range.start}_${range.end}`;

  useEffect(() => {
    let live = true;
    api.get<CalendarData>(`/calendar?start=${range.start}&end=${range.end}`).then(
      (data) => {
        cache.set(key, data);
        if (live) setLoaded({ key, data });
      },
      () => {},
    );
    return () => {
      live = false;
    };
  }, [key, range.start, range.end, tick]);

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 600_000); // the date and the open/closed state move on
    return () => clearInterval(t);
  }, []);

  const data = loaded?.key === key ? loaded.data : (cache.get(key) ?? null);
  const today = data?.today ?? iso(new Date());
  const month = parse(anchor).getMonth();
  const picked = data?.days.find((d) => d.date === selected) ?? null;
  const onToday = selected === today && today >= range.start && today <= range.end && (view === "week" || parse(today).getMonth() === month);

  function choose(v: View) {
    setView(v);
    setAnchor(selected);
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      // private window: the choice lasts until the page is closed
    }
  }
  function step(dir: 1 | -1) {
    const a = parse(anchor);
    const next = view === "week" ? addDays(a, 7 * dir) : new Date(a.getFullYear(), a.getMonth() + dir, 1);
    setAnchor(iso(next));
    if (view === "week") setSelected(iso(addDays(parse(selected), 7 * dir)));
  }
  function select(d: string) {
    setSelected(d);
    if (view === "month" && parse(d).getMonth() !== month) setAnchor(d);
  }
  function goToday() {
    setAnchor(today);
    setSelected(today);
  }

  const label =
    view === "month"
      ? fmt(anchor, { month: "long", year: "numeric" })
      : `${fmt(range.start, { day: "numeric", month: "short" })} – ${fmt(range.end, { day: "numeric", month: "short" })}`;
  const m = data?.market;
  const beyondList = !!data?.holidays_known_until && range.end > data.holidays_known_until;

  return (
    <section className={`text-muted ${className}`} aria-label="Trading calendar">
      <div className="flex items-center justify-between gap-2">
        <h2 className="whitespace-nowrap text-[13px] font-semibold text-text">Trading calendar</h2>
        <div role="tablist" aria-label="Calendar view" className="flex rounded-lg bg-surface-3 p-0.5 text-[11px]">
          {(["month", "week"] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              onClick={() => choose(v)}
              className={`rounded-md px-2 py-0.5 capitalize ${view === v ? "bg-surface font-semibold text-text shadow-xs" : "font-medium hover:text-text"}`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {m && (
        <p className="mt-2 flex items-center gap-1.5 text-[11px]">
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${m.state === "open" ? "animate-pulse bg-up" : m.state === "pre" ? "bg-gold" : "bg-subtle"}`} />
          {m.state === "open" ? (
            <span className="font-medium text-up">Market open · closes 3:30 PM</span>
          ) : m.state === "pre" ? (
            <span>Opens today at 9:15 AM</span>
          ) : (
            <span>
              Closed · opens <b className="font-semibold text-text">{fmt(m.next_open, { weekday: "short", day: "numeric", month: "short" })}</b>
            </span>
          )}
        </p>
      )}

      <div className="mt-2.5 flex items-center justify-between gap-1">
        <p className="font-display text-sm font-semibold text-text">{label}</p>
        <div className="flex items-center">
          {!onToday && (
            <button type="button" onClick={goToday} className="mr-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-strong hover:bg-surface-3">
              Today
            </button>
          )}
          {([-1, 1] as const).map((dir) => (
            <button
              key={dir}
              type="button"
              onClick={() => step(dir)}
              aria-label={`${dir < 0 ? "Previous" : "Next"} ${view}`}
              className="grid h-6 w-6 place-items-center rounded-md text-sm hover:bg-surface-3 hover:text-text"
            >
              {dir < 0 ? "‹" : "›"}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2">
        {!data ? (
          <div role="status" aria-label="Loading the calendar" className={`skeleton ${view === "month" ? "h-[196px]" : "h-[260px]"}`} />
        ) : view === "month" ? (
          <MonthGrid days={data.days} month={month} today={today} selected={selected} onSelect={select} />
        ) : (
          <WeekList days={data.days} today={today} selected={selected} onSelect={select} />
        )}
      </div>

      {view === "month" && data && (
        <>
          <div className="mt-2.5 min-h-[52px] rounded-lg border border-border bg-surface px-2.5 py-2 text-[11px] leading-snug">
            {picked ? (
              <>
                <p className="flex items-baseline justify-between gap-2 text-xs">
                  <b className="font-semibold text-text">{fmt(picked.date, { weekday: "short", day: "numeric", month: "short" })}</b>
                  {picked.date === today && <span className="font-medium text-brand-strong">today</span>}
                </p>
                <p
                  className={`num mt-0.5 ${
                    picked.status === "holiday" || picked.status === "special" ? "font-medium text-gold" : picked.nifty ? (picked.nifty.change_pct >= 0 ? "font-semibold text-up" : "font-semibold text-down") : ""
                  }`}
                >
                  {describe(picked, today)}
                  {picked.nifty && <span className="font-normal text-muted"> · {picked.nifty.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>}
                </p>
                <Extras d={picked} />
              </>
            ) : (
              <p>Pick a day to see it.</p>
            )}
          </div>
          <p className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[10px]">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ background: "color-mix(in oklab, var(--up) 45%, transparent)" }} /> Nifty up
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ background: "color-mix(in oklab, var(--down) 45%, transparent)" }} /> down
            </span>
            <span className="flex items-center gap-1">
              <span className="h-1 w-1 rounded-full bg-gold" /> holiday
            </span>
            <span className="flex items-center gap-1">
              <span className="h-1 w-1 rounded-full bg-brand" /> your dates
            </span>
          </p>
        </>
      )}
      {beyondList && data?.holidays_known_until && (
        <p className="mt-2 text-[10px] leading-snug">
          Holidays after {fmt(data.holidays_known_until, { month: "short", year: "numeric" })} aren&apos;t published yet, so later weekdays show as trading days.
        </p>
      )}
    </section>
  );
}
