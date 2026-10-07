"use client";

import { useId } from "react";

/** A tiny line (with a soft fill) for price widgets. Colour follows direction; the number beside it says the same in text. */
export function Sparkline({ data, height = 36, up, className = "" }: { data: number[]; height?: number; up?: boolean; className?: string }) {
  const id = useId();
  if (data.length < 2) return <div style={{ height }} />;
  const rising = up ?? data[data.length - 1] >= data[0];
  const color = rising ? "var(--up)" : "var(--down)";
  const lo = Math.min(...data);
  const hi = Math.max(...data);
  const span = hi - lo || 1;
  const W = 100;
  const pts = data.map((v, i) => [(i / (data.length - 1)) * W, 2 + (1 - (v - lo) / span) * (height - 4)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join("");
  return (
    <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className={`block w-full ${className}`} style={{ height }} aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.22} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={`${line}L${W},${height}L0,${height}Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
