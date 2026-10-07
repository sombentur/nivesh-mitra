"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Segmented, Skeleton, Spinner } from "@/components/ui";
import { api, type NewsItem, type NewsPulse as Pulse, type NewsTone } from "@/lib/api";
import { fmtDay } from "@/lib/format";

const TONE: Record<NewsTone, { label: string; cls: string; mark: string }> = {
  positive: { label: "Positive", cls: "bg-up-soft text-up", mark: "▲" },
  negative: { label: "Negative", cls: "bg-down-soft text-down", mark: "▼" },
  neutral: { label: "Neutral", cls: "bg-surface-3 text-muted", mark: "●" },
};

const OVERALL = {
  positive: { tone: "good", text: "Mostly positive" },
  negative: { tone: "bad", text: "Mostly negative" },
  mixed: { tone: "warn", text: "Mixed" },
  neutral: { tone: "neutral", text: "Mostly routine" },
  unrated: { tone: "neutral", text: "Not rated" },
} as const;

function ago(iso: string) {
  const mins = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}

function Headline({ n }: { n: NewsItem }) {
  const t = n.tone ? TONE[n.tone] : null;
  return (
    <li className="flex gap-3 rounded-xl border border-border bg-surface p-3 shadow-xs hover:border-border-strong">
      <span
        className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md text-[11px] font-bold ${t ? t.cls : "bg-surface-3 text-muted"}`}
        title={t?.label ?? "Not rated"}
      >
        {t?.mark ?? "·"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="rounded-md bg-navy px-1.5 py-0.5 font-semibold tracking-wide text-white">{n.symbol}</span>
          {n.role !== "heavyweight" && n.change_pct !== null && (
            <span className={`num font-semibold ${n.change_pct >= 0 ? "text-up" : "text-down"}`}>
              {n.role === "gainer" ? "Top gainer" : "Top loser"} {n.change_pct >= 0 ? "▲" : "▼"} {Math.abs(n.change_pct * 100).toFixed(1)}%
            </span>
          )}
          {n.kind !== "News" && <span className="text-muted">· exchange filing</span>}
        </p>
        {n.url ? (
          <a href={n.url} target="_blank" rel="noopener noreferrer" className="mt-1 block rounded text-sm font-medium leading-snug hover:text-brand-strong hover:underline">
            {n.title}
          </a>
        ) : (
          <p className="mt-1 text-sm font-medium leading-snug">{n.title}</p>
        )}
        {n.why && <p className="mt-1 text-xs leading-relaxed text-muted">{n.why}</p>}
        <p className="mt-1 text-[11px] text-muted">
          {n.source || "Trendlyne"} · {ago(n.published)}
        </p>
      </div>
    </li>
  );
}

/** Headlines for the market's heavyweights and today's biggest movers, tagged by Claude. Information, not a forecast. */
export function NewsPulse() {
  const [data, setData] = useState<Pulse | null>(null);
  const [lang, setLang] = useState<"en" | "kn">("en");
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get<Pulse>("/news").then(setData, () => {}), []);
  useEffect(() => {
    load();
  }, [load]);
  const running = busy || !!data?.refreshing;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      api.get<Pulse>("/news").then(
        (d) => {
          setData(d);
          if (!d.refreshing) setBusy(false);
        },
        () => setBusy(false),
      );
    }, 4000);
    return () => clearInterval(t);
  }, [running]);

  async function refresh() {
    setBusy(true);
    try {
      await api.post("/news/refresh");
    } catch {
      setBusy(false);
    }
  }

  const p = data?.pulse ?? null;
  const items = p ? (all ? p.items : p.items.slice(0, 8)) : [];
  const sc = data?.scorecard;
  return (
    <Card
      title="News pulse"
      subtitle="Latest headlines for the market's biggest companies and today's top movers."
      action={
        <Button variant="secondary" size="sm" onClick={refresh} disabled={running}>
          {running && <Spinner size={13} />}
          {running ? "Refreshing…" : "Refresh"}
        </Button>
      }
    >
      {!data ? (
        <div role="status" aria-label="Loading the news" className="grid gap-3">
          <Skeleton className="h-24 rounded-2xl" />
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        </div>
      ) : !p ? (
        <p className="rounded-xl border border-dashed border-border-strong p-6 text-center text-sm text-muted">
          No news collected in the last 24 hours. It&apos;s gathered at 8:40 AM and 3:45 PM on market days, or press Refresh.
        </p>
      ) : (
        <>
          <div className="rounded-2xl bg-gradient-to-br from-brand-soft to-info-soft p-4 ring-1 ring-inset ring-brand/15 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex flex-wrap items-center gap-2 text-sm">
                <Badge tone={OVERALL[p.overall].tone}>{OVERALL[p.overall].text}</Badge>
                <span className="num text-xs text-muted">
                  <span className="text-up">▲ {p.counts.positive}</span> · <span className="text-down">▼ {p.counts.negative}</span> · ● {p.counts.neutral} ·{" "}
                  {p.companies} companies · for {fmtDay(p.session)}
                </span>
              </span>
              {p.brief_kn && (
                <Segmented
                  label="Brief language"
                  value={lang}
                  onChange={setLang}
                  options={[
                    { value: "en", label: "English" },
                    { value: "kn", label: "ಕನ್ನಡ" },
                  ]}
                />
              )}
            </div>
            <p className="mt-3 text-[15px] leading-relaxed">{lang === "kn" && p.brief_kn ? p.brief_kn : p.brief_en}</p>
            <p className="mt-2 text-[11px] text-muted">
              {p.source === "claude" ? "Tone and summary by Claude, from these headlines only." : p.note ? `Plain summary (${p.note}).` : "Plain summary."} Not a
              forecast: markets often move against the news.
            </p>
          </div>
          <ul className="mt-4 grid grid-cols-1 gap-2 lg:grid-cols-2">
            {items.map((n) => (
              <Headline key={`${n.symbol}-${n.title}`} n={n} />
            ))}
          </ul>
          {p.items.length > 8 && (
            <button type="button" onClick={() => setAll(!all)} className="mt-3 rounded text-sm font-semibold text-brand-strong hover:underline">
              {all ? "Show fewer" : `Show all ${p.items.length} headlines`}
            </button>
          )}
        </>
      )}
      {sc && (
        <p className="mt-4 border-t border-border pt-3 text-xs leading-relaxed text-muted">
          {sc.days < sc.min_days
            ? `Keeping score: each market day the app checks whether a clearly positive or negative news tone matched the Nifty's move. ${sc.days} of ${sc.min_days} days collected so far.`
            : `News tone matched the Nifty's direction on ${sc.agreed} of ${sc.days} days (${Math.round((sc.agreed / sc.days) * 100)}%). A coin flip scores about 50%.`}
          {data?.claude && data.spend ? ` Claude this month: ₹${data.spend.inr.toFixed(0)} of ₹${data.spend.cap_inr.toLocaleString("en-IN")}.` : ""}
        </p>
      )}
    </Card>
  );
}
