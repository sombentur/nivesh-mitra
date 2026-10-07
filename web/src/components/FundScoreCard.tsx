import { Badge, Card, Notice } from "@/components/ui";
import type { FundScoring } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";

const pct = (v: number, d = 1) => `${(v * 100).toFixed(d)}%`;

/** Plain-language name and how to show each measure (doc 03 §C2). */
export const METRICS: Record<string, { label: string; fmt: (v: number) => string; hint: string }> = {
  rr1_med: { label: "Typical 1-year return", fmt: (v) => pct(v), hint: "Median of every 1-year period in the last 10 years" },
  rr3_med: { label: "Typical 3-year return", fmt: (v) => pct(v), hint: "Median of every 3-year period (per year)" },
  rr5_med: { label: "Typical 5-year return", fmt: (v) => pct(v), hint: "Median of every 5-year period (per year)" },
  rr7_med: { label: "Typical 7-year return", fmt: (v) => pct(v), hint: "Median of every 7-year period (per year)" },
  rr3_p10: { label: "Bad-case 3-year return", fmt: (v) => pct(v), hint: "9 in 10 three-year periods did at least this well" },
  beat_bench_3y: { label: "Beat the index fund", fmt: (v) => pct(v, 0), hint: "Share of 3-year periods it beat a cheap index fund on its benchmark" },
  beat_cat_3y: { label: "Beat the typical peer", fmt: (v) => pct(v, 0), hint: "Share of 3-year periods it beat the category median" },
  beat_cat_1y: { label: "Beat the typical peer (1-yr)", fmt: (v) => pct(v, 0), hint: "Share of 1-year periods it beat the category median" },
  maxdd_5y: { label: "Worst fall in 5 years", fmt: (v) => pct(v, 0), hint: "Biggest drop from a peak" },
  downcap_3y: { label: "Falls it took part in", fmt: (v) => pct(v, 0), hint: "In months the index fell, how much of that fall this fund took" },
  sortino_3y: { label: "Reward for the downs", fmt: (v) => v.toFixed(2), hint: "Sortino ratio: return above safe interest per unit of downside" },
  sharpe_3y: { label: "Reward for the ups and downs", fmt: (v) => v.toFixed(2), hint: "Sharpe ratio: return above safe interest per unit of volatility" },
  vol_3y: { label: "Bumpiness", fmt: (v) => pct(v), hint: "Yearly volatility of daily returns" },
  ter: { label: "Yearly cost (TER)", fmt: (v) => pct(v, 2), hint: "Total expense ratio of this plan, from AMFI" },
  tracking_error_1y: { label: "Tracking error (1 yr)", fmt: (v) => pct(v, 2), hint: "How much it wobbles around funds tracking the same index" },
  tracking_error_3y: { label: "Tracking error (3 yr)", fmt: (v) => pct(v, 2), hint: "" },
  tracking_diff_1y: { label: "Kept up with peers (1 yr)", fmt: (v) => pct(v, 2), hint: "Return vs the typical fund tracking the same index" },
  tracking_diff_3y: { label: "Kept up with peers (3 yr)", fmt: (v) => pct(v, 2), hint: "" },
  return_1y: { label: "1-year return", fmt: (v) => pct(v, 2), hint: "" },
  worst_1m: { label: "Worst 30 days", fmt: (v) => pct(v, 2), hint: "Catches credit accidents in debt funds" },
};

const MODEL_EXTRAS: Record<string, string[]> = {
  equity: ["manager_tenure", "aum_adequacy"],
  index: ["aum_adequacy"],
  debt: ["credit_quality"],
  liquid: [],
};

const MISSING_NOTE: Record<string, string> = {
  manager_tenure: "Fund manager tenure — no official data source yet",
  aum_adequacy: "Fund size (AUM) — coming soon",
  credit_quality: "Credit quality of holdings — needs portfolio disclosures",
};

export function FundScoreCard({ s }: { s: FundScoring }) {
  if (s.total === null) {
    return (
      <Card title="Score">
        <Notice>Not ranked: {s.unranked_reason ?? "not enough data"}.</Notice>
      </Card>
    );
  }
  const comps = Object.entries(s.components).sort((a, b) => b[1].weight - a[1].weight);
  const tone = s.confidence === "high" ? "good" : s.confidence === "medium" ? "warn" : "bad";
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-2">
          Score <span className="num text-3xl font-semibold tracking-tight">{s.total.toFixed(0)}</span>
          <span className="text-sm font-normal text-muted">/ 100</span>
          <Badge>
            #{s.rank} of {s.peers} {s.model === "index" ? `${s.peer_group} index funds` : s.peer_group}
          </Badge>
          <Badge tone={tone}>{s.confidence} confidence</Badge>
        </span>
      }
      subtitle={`Compared only with funds of the same kind. Rules v${s.rules_version}${s.as_of ? `, NAVs to ${fmtDate(s.as_of)}` : ""}. ${Math.round(s.coverage * 100)}% of the measures had data.`}
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <p className="font-display text-[15px] font-semibold">Strengths</p>
          <ul className="mt-2 grid gap-1.5 text-sm leading-relaxed">
            {s.reasons_for.length ? (
              s.reasons_for.map((r) => (
                <li key={r} className="flex gap-2">
                  <span className="font-semibold text-brand" aria-hidden="true">✓</span>
                  <span>{r}</span>
                </li>
              ))
            ) : (
              <li className="text-muted">Nothing stands out.</li>
            )}
          </ul>
          <p className="mt-5 font-display text-[15px] font-semibold">Watch out</p>
          <ul className="mb-4 mt-2 grid gap-1.5 text-sm leading-relaxed text-muted">
            {s.reasons_against.length ? (
              s.reasons_against.map((r) => (
                <li key={r} className="flex gap-2">
                  <span className="font-semibold text-warn" aria-hidden="true">!</span>
                  <span>{r}</span>
                </li>
              ))
            ) : (
              <li>No weak spots against its peers.</li>
            )}
          </ul>
          {s.regular_cost_10y_on_5000 !== null && (
            <Notice tone="warn">
              <span className="text-sm">
                The <b>Regular</b> plan of this fund would cost about <b>{inr(s.regular_cost_10y_on_5000)}</b> more over 10 years on a ₹5,000 monthly
                SIP (its yearly cost is {pct(s.metrics.regular_cost_gap ?? 0, 2)} higher). Always choose Direct.
              </span>
            </Notice>
          )}
        </div>
        <div>
          <p className="font-display text-[15px] font-semibold">How it compares, measure by measure</p>
          <p className="mt-0.5 text-xs text-muted">Bar = better than this share of its peers. Points = the measure&apos;s weight in the score.</p>
          <ul className="mt-3 grid gap-2.5">
            {comps.map(([k, c]) => {
              const m = METRICS[k];
              return (
                <li key={k} className="text-sm" title={m?.hint}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span>{m?.label ?? k}</span>
                    <span className="num text-muted">
                      <b className="text-text">{m ? m.fmt(c.value) : c.value}</b> · {c.weight} pts
                    </span>
                  </div>
                  <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-3" role="meter" aria-valuenow={c.percentile} aria-valuemin={0} aria-valuemax={100} aria-label={`${m?.label ?? k}: better than ${c.percentile.toFixed(0)}% of peers`}>
                    <div className="h-full rounded-full bg-[var(--series-1)]" style={{ width: `${Math.max(2, c.percentile)}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
          {(MODEL_EXTRAS[s.model] ?? []).some((k) => !(k in s.components)) && (
            <p className="mt-3 text-xs text-muted">
              Not scored yet:{" "}
              {(MODEL_EXTRAS[s.model] ?? [])
                .filter((k) => !(k in s.components))
                .map((k) => MISSING_NOTE[k])
                .join(" · ")}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
