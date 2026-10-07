"use client";

import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

type Point = [string, number]; // [ISO date, value]

/** A time-range button above the chart. `days: 0` means "everything there is". */
export type ChartRange = { key: string; label: string; days: number };

const PAD = { top: 14, right: 66, bottom: 26, left: 6 };
const DAY = 86400000;

function niceTicks(min: number, max: number, count = 5): number[] {
  const span = max - min || 1;
  const mag = 10 ** Math.floor(Math.log10(span / count));
  // the "nice" step whose tick count lands closest to what we asked for
  const step = [1, 2, 2.5, 5, 10, 20]
    .map((m) => m * mag)
    .reduce((best, s) => (Math.abs(span / s - count) < Math.abs(span / best - count) ? s : best));
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + 1e-9; v += step) ticks.push(Number(v.toFixed(6)));
  return ticks;
}

const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(2)}%`;

/**
 * Price chart for one series: a 2px line over a soft fill, the price scale on the right with the latest value tagged,
 * a dashed line at the period's starting value, and a crosshair that snaps to the nearest day (mouse, touch or arrow keys).
 * The line is a neutral blue; rises and falls are said in words and arrows beside it, in the usual green and red.
 */
export function LineChart({
  data,
  valueLabel,
  format,
  height: H = 280,
  color = "var(--chart-line)",
  area = true,
  ranges,
  defaultRange,
}: {
  data: Point[];
  valueLabel: string;
  format: (v: number) => string;
  height?: number;
  color?: string;
  area?: boolean;
  ranges?: readonly ChartRange[];
  defaultRange?: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [W, setW] = useState(800); // drawn at the real width so text stays 11px in any card
  const [rangeKey, setRangeKey] = useState(defaultRange ?? ranges?.[ranges.length - 1]?.key ?? "");
  const gradId = useId();

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // only offer ranges the history can actually fill (a 2-year-old fund has no 5-year view)
  const offered = useMemo(() => {
    if (!ranges || data.length < 2) return [];
    const spanDays = (new Date(data[data.length - 1][0]).getTime() - new Date(data[0][0]).getTime()) / DAY;
    return ranges.filter((r) => r.days === 0 || r.days <= spanDays * 1.05);
  }, [ranges, data]);
  const active = offered.find((r) => r.key === rangeKey) ?? offered[offered.length - 1] ?? null;

  const shown = useMemo(() => {
    if (!active || !active.days || data.length < 2) return data;
    const from = new Date(data[data.length - 1][0]).getTime() - active.days * DAY;
    const cut = data.filter(([d]) => new Date(d).getTime() >= from);
    return cut.length >= 2 ? cut : data;
  }, [data, active]);

  const geo = useMemo(() => {
    if (shown.length < 2) return null;
    const xs = shown.map(([d]) => new Date(d).getTime());
    const ys = shown.map(([, v]) => v);
    const x0 = xs[0], x1 = xs[xs.length - 1];
    const lo = Math.min(...ys), hi = Math.max(...ys);
    const padY = (hi - lo) * 0.08 || 1;
    const y0 = lo - padY, y1 = hi + padY;
    const sx = (t: number) => PAD.left + ((t - x0) / (x1 - x0)) * (W - PAD.left - PAD.right);
    const sy = (v: number) => PAD.top + (1 - (v - y0) / (y1 - y0)) * (H - PAD.top - PAD.bottom);
    const path = xs.map((t, i) => `${i ? "L" : "M"}${sx(t).toFixed(1)},${sy(ys[i]).toFixed(1)}`).join("");
    const fill = `${path}L${sx(x1).toFixed(1)},${H - PAD.bottom}L${sx(x0).toFixed(1)},${H - PAD.bottom}Z`;
    const yTicks = niceTicks(y0, y1, H < 240 ? 4 : 5);
    const days = (x1 - x0) / DAY;
    const years = days / 365.25;
    const xTicks: number[] = [];
    let xFormat: Intl.DateTimeFormatOptions;
    if (days <= 100) {
      // weeks: every Monday up to ~7 weeks, then every other one
      const step = days <= 50 ? 7 : 14;
      const d = new Date(x0);
      let t = new Date(d.getFullYear(), d.getMonth(), d.getDate() + ((8 - d.getDay()) % 7));
      for (; t.getTime() <= x1; t = new Date(t.getFullYear(), t.getMonth(), t.getDate() + step)) xTicks.push(t.getTime());
      xFormat = { day: "numeric", month: "short" };
    } else if (years < 2) {
      // month starts: every month under ~9 months (every other one on narrow charts), else quarter starts
      const step = years < 0.75 ? (W < 480 ? 2 : 1) : 3;
      const d = new Date(x0);
      let t = new Date(d.getFullYear(), Math.floor(d.getMonth() / step) * step + step, 1);
      for (; t.getTime() <= x1; t = new Date(t.getFullYear(), t.getMonth() + step, 1)) xTicks.push(t.getTime());
      xFormat = { month: "short", year: "2-digit" };
    } else {
      const yearStep = Math.max(1, Math.ceil(years / (W < 480 ? 4 : 6)));
      for (let y = new Date(x0).getFullYear() + 1; y <= new Date(x1).getFullYear(); y += yearStep) xTicks.push(new Date(y, 0, 1).getTime());
      xFormat = { year: "numeric" };
    }
    // keep labels clear of each other and of the two edges
    const minGap = W < 480 ? 44 : 56;
    const spaced = xTicks.filter((t) => sx(t) > PAD.left + 18 && sx(t) < W - PAD.right - 12).filter((t, i, all) => i === 0 || sx(t) - sx(all[i - 1]) >= minGap);
    const first = ys[0], last = ys[ys.length - 1];
    return { xs, ys, sx, sy, path, fill, yTicks, xTicks: spaced, xFormat, first, last, hi, lo, change: first ? last / first - 1 : 0 };
  }, [shown, H, W]);

  if (!geo)
    return (
      <div ref={boxRef}>
        <p className="text-sm text-muted">Not enough history to draw a chart.</p>
      </div>
    );

  function onMove(e: PointerEvent<SVGSVGElement>) {
    const box = svgRef.current!.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * W;
    let lo = 0, hi = geo!.xs.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (geo!.sx(geo!.xs[mid]) < x) lo = mid;
      else hi = mid;
    }
    setHover(Math.abs(geo!.sx(geo!.xs[lo]) - x) < Math.abs(geo!.sx(geo!.xs[hi]) - x) ? lo : hi);
  }

  function onKey(e: KeyboardEvent<SVGSVGElement>) {
    const n = geo!.xs.length;
    const step = e.shiftKey ? Math.max(1, Math.round(n / 20)) : 1;
    if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? n - 1) - step));
    else if (e.key === "ArrowRight") setHover((h) => Math.min(n - 1, (h ?? n - 1) + step));
    else if (e.key === "Home") setHover(0);
    else if (e.key === "End") setHover(n - 1);
    else if (e.key === "Escape") setHover(null);
    else return;
    e.preventDefault();
  }

  const at = hover !== null && hover < geo.xs.length ? hover : null;
  const hx = at !== null ? geo.sx(geo.xs[at]) : 0;
  const hy = at !== null ? geo.sy(geo.ys[at]) : 0;
  const day = (t: number, o: Intl.DateTimeFormatOptions) => new Date(t).toLocaleDateString("en-IN", o);
  const fullDate = (t: number) => day(t, { day: "numeric", month: "short", year: "numeric" });
  const plotRight = W - PAD.right;
  const lastY = geo.sy(geo.last);
  const up = geo.change >= 0;
  const hoverChange = at !== null && geo.first ? geo.ys[at] / geo.first - 1 : 0;

  return (
    <figure className="grid gap-2.5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-muted">
          <span className={`num text-sm font-semibold ${up ? "text-up" : "text-down"}`}>
            {up ? "▲" : "▼"} {signed(geo.change)}
          </span>
          <span>{active?.days ? `in ${active.label}` : `since ${fullDate(geo.xs[0])}`}</span>
          <span className="num whitespace-nowrap">
            High <b className="font-semibold text-text">{format(geo.hi)}</b>
          </span>
          <span className="num whitespace-nowrap">
            Low <b className="font-semibold text-text">{format(geo.lo)}</b>
          </span>
        </p>
        {offered.length > 1 && (
          <div role="group" aria-label="Time range" className="flex gap-0.5 rounded-lg bg-surface-2 p-0.5 ring-1 ring-inset ring-border">
            {offered.map((r) => (
              <button
                key={r.key}
                type="button"
                aria-pressed={r.key === active?.key}
                onClick={() => {
                  setRangeKey(r.key);
                  setHover(null);
                }}
                className={`num rounded-md px-2.5 py-1 text-xs ${r.key === active?.key ? "bg-navy font-semibold text-white shadow-xs" : "font-medium text-muted hover:text-text"}`}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="relative" ref={boxRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="num h-auto w-full touch-pan-y select-none rounded-lg"
          onPointerMove={onMove}
          onPointerDown={onMove}
          onPointerLeave={() => setHover(null)}
          onKeyDown={onKey}
          onBlur={() => setHover(null)}
          tabIndex={0}
          role="img"
          aria-label={`${valueLabel} from ${fullDate(geo.xs[0])} to ${fullDate(geo.xs[geo.xs.length - 1])}: ${format(geo.first)} to ${format(geo.last)}, ${up ? "up" : "down"} ${signed(Math.abs(geo.change)).replace("+", "")}. High ${format(geo.hi)}, low ${format(geo.lo)}. Use the arrow keys to read each day.`}
        >
          <defs>
            <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="70%" stopColor={color} stopOpacity={0.04} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          {geo.yTicks.map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={plotRight} y1={geo.sy(v)} y2={geo.sy(v)} stroke="var(--border)" strokeWidth={1} />
              {Math.abs(geo.sy(v) - lastY) > 13 && (
                <text x={plotRight + 8} y={geo.sy(v)} dominantBaseline="middle" fontSize={11} fill="var(--muted)">
                  {format(v)}
                </text>
              )}
            </g>
          ))}
          {geo.xTicks.map((t) => (
            <text key={t} x={geo.sx(t)} y={H - 7} textAnchor="middle" fontSize={11} fill="var(--muted)">
              {day(t, geo.xFormat)}
            </text>
          ))}
          {/* where the period started: above it you are up, below it you are down */}
          <line x1={PAD.left} x2={plotRight} y1={geo.sy(geo.first)} y2={geo.sy(geo.first)} stroke="var(--subtle)" strokeWidth={1} strokeDasharray="3 4" />
          {area && <path d={geo.fill} fill={`url(#${gradId})`} />}
          <path key={`${active?.key}-${shown.length}`} d={geo.path} pathLength={1} className="nm-draw" fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {/* the latest value, tagged on the price scale */}
          <circle cx={geo.sx(geo.xs[geo.xs.length - 1])} cy={lastY} r={3.5} fill={color} stroke="var(--surface)" strokeWidth={2} />
          <g>
            <rect x={plotRight + 4} y={lastY - 10} width={PAD.right - 6} height={20} rx={6} fill={color} />
            <text x={plotRight + 4 + (PAD.right - 6) / 2} y={lastY + 0.5} textAnchor="middle" dominantBaseline="middle" fontSize={11} fontWeight={600} fill="var(--surface)">
              {format(geo.last)}
            </text>
          </g>
          {at !== null && (
            <g pointerEvents="none">
              <line x1={hx} x2={hx} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--muted)" strokeWidth={1} strokeDasharray="3 3" />
              <line x1={PAD.left} x2={plotRight} y1={hy} y2={hy} stroke="var(--muted)" strokeWidth={1} strokeDasharray="3 3" opacity={0.6} />
              <circle cx={hx} cy={hy} r={5} fill={color} stroke="var(--surface)" strokeWidth={2} />
            </g>
          )}
        </svg>
        {at !== null && (
          <div
            className="glass pointer-events-none absolute top-1 z-10 rounded-xl border border-border px-3 py-2 text-xs"
            style={{ left: `${(hx / W) * 100}%`, transform: hx > W * 0.6 ? "translateX(calc(-100% - 12px))" : "translateX(12px)" }}
          >
            <div className="whitespace-nowrap text-muted">{fullDate(geo.xs[at])}</div>
            <div className="mt-0.5 flex items-center gap-1.5 whitespace-nowrap">
              <span className="inline-block h-0.5 w-3 rounded" style={{ background: color }} />
              {valueLabel} <b className="num text-sm">{format(geo.ys[at])}</b>
            </div>
            <div className={`num mt-0.5 whitespace-nowrap font-medium ${hoverChange >= 0 ? "text-up" : "text-down"}`}>
              {signed(hoverChange)} <span className="font-normal text-muted">from the start</span>
            </div>
          </div>
        )}
      </div>
    </figure>
  );
}
