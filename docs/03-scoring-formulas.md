# 03 — Scoring Formulas (Risk Profile, Stocks, Mutual Funds)

> **Read this first.** Every formula below is a transparent, rule-based heuristic.
> It is not advice from a SEBI-registered adviser. Every weight and threshold lives in a
> rules file (`backend/app/rules/*.yaml`; the risk profile is in `profile.yaml`) so you can see and change it. Every
> recommendation records the exact **model version** it came from, so the scorecard stays honest
> when the weights change.
>
> The AI layer never produces or changes a number. All scores and ranges come from these formulas.

---

## Part A — Risk profile (onboarding)

### A1. The 10 questions

| # | Question | Used for |
|---|----------|----------|
| 1 | Age | Capacity score |
| 2 | Monthly take-home income (range) | Emergency fund, EMI burden |
| 3 | Monthly household expenses | Emergency fund target |
| 4 | Amount you can invest each month | SIP planning, budget checks |
| 5 | Savings you could use in an emergency (₹). Months covered = savings ÷ expenses, rounded **down** | Capacity score, "emergency fund first" rule |
| 6 | Total EMIs per month | Capacity score (EMI ÷ income) |
| 7 | Main investment horizon (< 1 yr / 1–3 / 3–5 / 5+) | Capacity score |
| 8 | If your investments fell 20% in a month, you would… (sell / hold / buy more) | Tolerance |
| 9 | Investing experience (none / MF only / stocks < 2 yrs / stocks 2+ yrs) | Tolerance cap |
| 10 | Goals (name, type, target amount in today's ₹, target year) | Goal planner |

Tax regime (old or new) is asked in Settings rather than the questionnaire, because it only matters for ELSS (Phase 2).

### A2. Risk capacity (what you can afford), max 16 points

| Factor | 4 pts | 3 pts | 2 pts | 1 pt |
|---|---|---|---|---|
| Age | < 30 | 30–39 | 40–49 | 50+ |
| Horizon | 5+ yrs | 3–5 | 1–3 | < 1 |
| EMI ÷ income (lower end of your income range) | none | ≤ 20% | ≤ 40% | > 40% |
| Emergency fund | 6+ months | 3–6 | < 3 | none |

Capacity: **13–16 → Aggressive**, **9–12 → Moderate**, **≤ 8 → Conservative**.

### A3. Risk tolerance (what you can stomach)

- Reaction to a 20% fall: sell → Conservative, hold → Moderate, buy more → Aggressive.
- Experience cap: "none" or "MF only" caps tolerance at **Moderate** for the first 12 months.
  You can override this, but the app shows a warning and logs the override.

### A4. Final profile

```
profile = the LOWER of (capacity, tolerance)
```

The profile follows the stricter of the two. Being able to *afford* risk doesn't help if you would panic-sell,
and wanting risk doesn't help if you can't afford a loss.

Hard overrides:
- Horizon < 1 year → **Conservative**.
- No emergency fund → the profile is still computed, but the **first recommended action is always**:
  "Put ₹X/month into a liquid fund until you have 6 months of expenses (₹Y)."

### A5. Default asset split (you can edit it)

| Bucket | Conservative | Moderate | Aggressive |
|---|---|---|---|
| Core — mutual funds via SIP | 90% | 75% | 65% |
| Satellite — long-term direct stocks | 10% | 20% | 25% |
| Trading — short-term ideas (Phase 2) | 0% | 5% | 10% |

Warnings when you edit the split (warn, don't block — rule R-08 in doc 04 handles enforcement):
- Trading > 10% → strong warning. Hard ceiling 20% (refused above). Raising the trading share needs a typed reason and only takes effect after a 24-hour delay; lowering it is immediate.
- Emergency fund routing while it's being built: 100% of the monthly investable amount goes to a liquid fund until 3 months are covered, then 50% until 6 months.
- While trading is locked, its share stays in mutual funds (core).
- Satellite > 35% → warning.
- Core < 50% → warning.
- Trading bucket stays at 0% until the emergency fund is ≥ 3 months **and** paper trading is complete.

Re-run prompt: every 12 months, or when you change income, EMI or goal answers.

---

## Part B — Long-term stock score (0–100)

### B1. Universe

Nifty 500 constituents, refreshed from the official niftyindices.com list twice a year. Any stock you search for is
also scored against the same peer groups.

### B2. Hard exclusions (not scored; the reason is shown)

| Code | Rule (defaults, configurable) |
|---|---|
| E1 Penny / micro | Price < ₹20 **or** market cap < ₹1,000 cr |
| E2 Illiquid | Median daily traded value over last 60 sessions < ₹5 cr |
| E3 Loss-making | Net profit (trailing 12 months) < 0, **or** a loss in 2 of the last 3 financial years |
| E4 Regulatory | Under exchange ASM/GSM surveillance, trading suspended, or a SEBI order against the company/promoters in the last 24 months |
| E5 Audit | Auditor resigned mid-term in the last 24 months, **or** a qualified/adverse opinion in the latest annual report |
| E6 Heavy pledge | Promoter pledge > 25% of promoter holding |
| E7 Too new | Listed < 3 years (not enough history — shown as "Not scored yet") |

### B3. Sector-relative percentiles

Each metric is converted to a **percentile rank within the stock's sector** (0 = worst peer, 100 = best).
If a sector has fewer than 8 scorable stocks, the broader sector group is used, then the whole universe.
Percentiles are robust to outliers and make a "good ROE" mean the same thing in IT and in cement.

```
pct(x) = 100 × (number of peers with a worse value) / (number of peers − 1)
```

For metrics where lower is better (D/E, P/E, PEG), the ranking is reversed.

### B4. Standard model (non-financial companies)

| Pillar | Weight | Metric (points) | Notes |
|---|---|---|---|
| **Quality** | 30 | ROE, 3-yr average (8) · ROCE, 3-yr average (10) · Positive free-cash-flow years out of last 5 (6) · Cash conversion: Σ CFO ÷ Σ PAT over 5 yrs (6) | FCF years scored absolutely: 5→100, 4→75, 3→40, ≤2→0 |
| **Growth** | 25 | Revenue CAGR 3 yr (6) · Revenue CAGR 5 yr (5) · PAT CAGR 3 yr (8) · PAT CAGR 5 yr (6) | If base-year PAT ≤ 0, that CAGR scores 0 with reason "base year was a loss" |
| **Financial strength** | 15 | Debt-to-equity (8, lower better; D/E ≤ 0.1 → 100) · Interest coverage = EBIT ÷ interest (7) | |
| **Valuation** | 20 | P/E vs sector median (7) · P/E vs own 5-yr median (7) · PEG = P/E ÷ PAT CAGR 3 yr (6) | PEG undefined when growth ≤ 0 → scores 0 |
| **Ownership** | 10 | Promoter holding change over 4 quarters (4) · Pledge (3) · FII + DII holding change over 4 quarters (3) | Pledge scored absolutely: 0% → 100, ≤ 5% → 60, ≤ 10% → 30, > 10% → 0 |

```
raw_score = Σ (metric_weight × metric_percentile / 100)        → 0..100
```

**Missing data:** a metric with no data is dropped and the remaining weights are rescaled.
If more than 20% of the weight is missing, confidence is set to Low. If more than 40% is missing, the stock is "Not scored — insufficient data".
Missing data never *raises* a score.

### B5. Financials model (banks, NBFCs, insurers)

D/E, ROCE and free cash flow don't mean the same thing for lenders, so these companies use:

| Pillar | Weight | Metrics |
|---|---|---|
| Quality | 30 | ROA 3-yr avg (12) · ROE 3-yr avg (12) · Gross NPA % (6, lower better, if available) |
| Growth | 25 | Loan book / revenue CAGR 3 yr (10) · PAT CAGR 3 yr (10) · PAT CAGR 5 yr (5) |
| Strength | 15 | Capital adequacy ratio (15, if available) |
| Valuation | 20 | P/B vs sector (10) · P/B vs own 5-yr median (10) |
| Ownership | 10 | Same as standard |

If the data vendor lacks NPA or capital adequacy, those weights are rescaled and the card shows
"Bank/NBFC — scored with limited data".

### B6. Red-flag penalties (applied after weighting; floor 0)

| Flag | Penalty | Always shown as a red flag? |
|---|---|---|
| Any promoter pledge (> 0%) | −3 | Yes |
| Pledge increased in the last 2 quarters | −5 | Yes |
| Promoter holding fell > 5 percentage points in 4 quarters | −5 | Yes |
| D/E > 2 (non-financial) | −5 | Yes |
| Operating cash flow negative in 2 of the last 3 years | −5 | Yes |
| Price > 30% below 200-day average ("falling knife") | 0 (informational) | Yes |

```
final_score = max(0, raw_score − Σ penalties)
```

### B7. Rating and action

| Score | Label | Action shown |
|---|---|---|
| 75–100 | Strong candidate | **Buy** if price is inside the buy range; otherwise **Wait for price** |
| 60–74 | Decent | **Watch** |
| 45–59 | Neutral | **No action** |
| < 45 | Weak | **Avoid** |

Any **BLOCK** from the risk engine (doc 04) overrides the action, for example "Buy" becomes "Blocked: would make this stock 14% of your portfolio".

### B8. Confidence

- **High:** ≥ 90% of weight has data, ≥ 5 years of history, peer group ≥ 15, no red flags.
- **Medium:** ≥ 75% of weight has data.
- **Low:** anything else, or any red flag.

### B9. Reasons for and against

Take every metric's `(percentile − 50) × weight`.
- **Top 3 positive** → "Reasons FOR", e.g. *"Return on capital 24% — better than 88% of cement companies."*
- **Top 3 negative** plus all red flags → "Reasons AGAINST".

The templates fill in real numbers. The AI layer (if enabled) may reword them but may not add numbers (see doc 01, §6).

### B10. Fair value range and buy range (standard model)

Requires trailing-12-month EPS > 0. Otherwise the card shows "Fair value not estimable (no profits)".

```
PE_own_p25, PE_own_med, PE_own_p75  = percentiles of the stock's own daily P/E over the last 5 years
PE_sec_p25, PE_sec_med, PE_sec_p75  = percentiles of current P/E among profitable sector peers

FV_low  = EPS_ttm × (0.5 × PE_own_p25 + 0.5 × PE_sec_p25)
FV_mid  = EPS_ttm × (0.5 × PE_own_med + 0.5 × PE_sec_med)
FV_high = EPS_ttm × (0.5 × PE_own_p75 + 0.5 × PE_sec_p75)

Buy range = FV_low  →  0.95 × FV_mid          (at least a 5% margin of safety)
```

- Price > buy range → "Wait — currently ₹X above the buy range".
- Price < 0.8 × FV_low → "Unusually cheap — check the news for why before buying" (value-trap warning).
- The financials model uses P/B and book value per share (BVPS) the same way.

### B11. Expected 3-year return range (illustrative, annualised)

```
g_cons = max(0, 0.5 × min(PAT_CAGR_3y, PAT_CAGR_5y))
g_exp  = min(median(PAT_CAGR_3y, PAT_CAGR_5y, Rev_CAGR_3y), 18%)
g_opt  = min(max(PAT_CAGR_3y, PAT_CAGR_5y), 25%)

exit_PE: cons = blended p25, exp = blended median, opt = blended p75   (from B10)

return = ((EPS_ttm × (1 + g)^3 × exit_PE) / price)^(1/3) − 1 + dividend_yield
```

This range can be negative, and it is shown that way. It is labelled *"Illustration based on history, not a promise."*

---

## Part C — Mutual fund score (compared only within the same SEBI category)

### C1. Scope

- Only **Direct – Growth** plans are scored. Regular plans are mapped to their Direct twin for cost comparison.
- A category needs at least 5 funds with 3+ years of history to be scored. Otherwise funds are shown "unranked".

### C2. Metrics (computed from daily NAV)

| Metric | Definition |
|---|---|
| `RR3_med`, `RR5_med`, `RR7_med` | Median of **rolling** 3/5/7-year CAGRs, taking a window ending on every trading day over the last ≤ 10 years |
| `RR3_p10` | 10th-percentile rolling 3-yr CAGR (a realistic "bad case") |
| `Beat_bench_3y` | % of rolling 3-yr windows where the fund's CAGR > its benchmark TRI (Total Return Index) CAGR. Falls back to the category median fund if the TRI is unavailable |
| `Beat_cat_3y` | % of rolling 3-yr windows where the fund's CAGR > the category median CAGR |
| `Vol_3y` | Annualised standard deviation of daily returns, 3 years: `σ_daily × √252` |
| `Sharpe_3y` | `(CAGR_3y − rf) / Vol_3y`, with `rf` = configurable risk-free rate (default 6.5%) |
| `Sortino_3y` | `(CAGR_3y − rf) / downside_deviation_3y` |
| `MaxDD_5y` | Largest peak-to-trough NAV fall in 5 years (or since launch) |
| `DownCap_3y` | Downside capture ratio vs benchmark on monthly returns (lower is better) |
| `TER` | Direct-plan expense ratio (latest) |
| `Tenure` | Current fund manager's years on this fund |
| `AUM` | ₹ crore |

### C3. Weights — equity and hybrid categories

| Pillar | Weight | Metrics (points) |
|---|---|---|
| Rolling returns | 25 | RR3_med (8) · RR5_med (10) · RR7_med (7) |
| Consistency | 20 | Beat_bench_3y (10) · Beat_cat_3y (10) |
| Downside protection | 20 | MaxDD_5y (7) · DownCap_3y (7) · RR3_p10 (6) |
| Risk-adjusted | 15 | Sortino_3y (8) · Sharpe_3y (7) |
| Cost | 10 | TER (lower better) |
| Stability | 10 | Manager tenure (5: ≥ 5 yrs → 100, 3–5 → 70, 2–3 → 40, < 2 → 10) · AUM adequacy (5: < ₹500 cr → 20, otherwise 100; small-cap > ₹30,000 cr → 60) |

Each metric is a percentile within the category, and the formula is the same as B4. Missing metrics are rescaled the same way:
for example, a 4-year-old fund has no RR5 or RR7, so its confidence is Low.

### C3a. As built (30-Sep-2026) — rules in `backend/app/rules/mf_scoring.yaml`

- **Benchmark stand-in:** until official TRI data is added, each active equity category is compared with the
  longest-running index fund on its usual benchmark (Large Cap → Nifty 50, Flexi/Multi/Focused/Value/ELSS → Nifty 500,
  Mid Cap → Midcap 150, Small Cap → Smallcap 250). That fund's NAV is after its own small costs — and it's exactly the
  cheap alternative you could buy instead.
- **Not applicable ≠ missing:** where a category has no stand-in (e.g. hybrid), "beat the index" and downside capture
  are left out of the model entirely, so they don't lower confidence. Genuinely missing data (manager tenure, fund size,
  debt credit quality — no official machine-readable source yet) is rescaled and does lower confidence.
- **Index funds** are grouped by the index they track (matched on the fund name) and compared on cost and on how closely
  they follow the typical fund tracking that index (a "median fund" built from the group's daily returns).
- **Expense ratios** come from AMFI's monthly TER file (daily rows, Direct and Regular), matched to schemes by name
  (99%+ match). The Direct↔Regular TER gap gives the rupee cost of a Regular plan (§C9).
- Scores are recalculated every Saturday and after new fund history downloads; the last 8 runs are kept.

### C4. Other categories

| Category | Weights |
|---|---|
| **Index funds / ETFs** | Tracking error 1y/3y (35) · TER (35) · Tracking difference (20) · AUM (10) |
| **Debt** (short duration, corporate bond, banking & PSU, gilt) | RR1_med + RR3_med (25) · Consistency (15) · Volatility + MaxDD (20) · TER (20) · Credit quality: % AAA/sovereign (20, needs portfolio data) |
| **Liquid / overnight / money market** | TER (40) · 1-yr return percentile (30) · Worst 1-month return (30 — catches credit accidents) |

### C5. Actions for funds you hold

| Condition | Action |
|---|---|
| Score in top half of category | **Continue SIP** |
| Below category median for 4+ consecutive quarters, **or** a monitoring alert (C8) | **Review** — shows the best alternative, plus the exit load and tax cost of switching |
| Bottom quartile for 6+ quarters **and** alternative saves cost after tax | **Consider switching** (you decide; switching is never urgent) |

### C6. Suggested portfolio (3–5 funds) — templates by profile, for goals 5+ years away

| Slot | Conservative | Moderate | Aggressive |
|---|---|---|---|
| Nifty 50 / large-cap index fund | 35% | 35% | 30% |
| Flexi-cap fund | 15% | 25% | 25% |
| Mid-cap fund | — | 15% | 20% |
| Small-cap fund | — | — | 10% |
| Balanced advantage (dynamic asset allocation) | 20% | — | — |
| Short-duration / corporate-bond debt fund | 30% | 25% | 15% |

Horizon adjustments per goal:
- **3–5 yrs** → equity capped at 50%, the rest in hybrid/debt.
- **1–3 yrs** → equity capped at 20%.
- **< 1 yr** → liquid / arbitrage fund only.

Fund selection: the **top-scored Direct fund** in each slot's category, then an overlap check:

```
overlap(A, B) = Σ over common stocks of min(weight_in_A, weight_in_B)
```

If two active equity funds overlap > 50%, the lower-scored one is replaced by the next-best in its category.
The overlap % is always shown.

### C7. SIP calculator and required SIP

Goals only have a year, so the plan counts to the **middle (July) of the goal year** — cautious for a goal that turns out
to be early in that year. A goal under 12 months away is 100% liquid fund.

Scenario returns are **category assumptions** (nominal, pre-tax, configurable), deliberately *not* the fund's recent past,
so that one hot year doesn't inflate your plan:

| Category | Conservative | Expected | Optimistic |
|---|---|---|---|
| Large cap / index | 7% | 10% | 12% |
| Flexi cap | 7% | 11% | 13% |
| Mid cap | 6% | 12% | 15% |
| Small cap | 5% | 12% | 16% |
| Balanced advantage | 6% | 9% | 11% |
| Short-duration debt | 5.5% | 6.5% | 7.5% |
| Liquid | 5% | 6% | 6.5% |

A portfolio's scenario return is the weight-averaged category return.

```
i          = (1 + r)^(1/12) − 1                       effective monthly rate
FV(SIP P)  = P × ((1 + i)^n − 1) / i × (1 + i)        n = months, paid at start of month
Target     = amount_today × (1 + inflation)^years     inflation default 6%, education 8%
SIP needed = Target / [((1 + i)^n − 1) / i × (1 + i)]
```

- **"Recommended SIP"** uses the **Conservative** rate, so you are more likely to reach the goal.
- The Expected and Optimistic figures show "if things go normally / well".
- An optional yearly step-up (e.g. +10%/year) is supported.

### C8. Monitoring alerts (checked weekly and after each monthly factsheet)

| Alert | Trigger |
|---|---|
| Underperformance | Below category median on trailing 1-yr return at 4+ consecutive quarter-ends |
| Manager change | Fund manager name differs from the previous month's record |
| Expense increase | TER up ≥ 0.15 percentage points, or ≥ 20% relative, vs 3 months ago |
| Category / style change | SEBI category changed, or large/mid/small-cap mix shifted > 15 points in 6 months |

### C9. Direct vs Regular cost difference (₹ over 10 years)

```
gross = expected_return + TER_direct
FV_direct  = FV(amount, gross − TER_direct,  10 yrs)
FV_regular = FV(amount, gross − TER_regular, 10 yrs)
Cost of Regular = FV_direct − FV_regular      (shown in ₹ for your actual SIP/lumpsum)
```

### C10. Rebalancing

- Drift per bucket = actual % − target %.
- Any |drift| > **5 points** → suggestion.
- **First choice:** redirect new SIPs/lumpsums, which costs no tax.
- Selling is suggested only when |drift| > 10 points. It then shows exit load and estimated tax, and prefers units held > 12 months, within the yearly LTCG exemption.

---

## Part D — Short-term / swing ideas (built early, practice-only — rules in `backend/app/rules/trading.yaml`)

- **Universe:** the 200 most-traded NSE "EQ" stocks priced ≥ ₹100 with a typical day's turnover ≥ ₹20 crore
  (median over 60 sessions), ETFs excluded. Re-ranked monthly. (Groww's instrument list has no index membership, so
  liquidity stands in for "Nifty 200"; you can later upload the official list.)
- **Delivery only** (buy one day, sell on a later day). Signals use the day's close; you buy the next session.
- **Setup 1 — Pullback in an uptrend:** close > 200-DMA, 50-DMA > 200-DMA, low touched the 20-DMA (within 1%) in the
  last 3 days, close back above the 20-DMA, RSI(14) 40–60, green day. Stop = higher of (entry − 2×ATR) and
  (5-day low − 0.2×ATR). Target 2R. Max hold 10 sessions. Entry range ±0.5% of the close.
- **Setup 2 — Breakout on high volume:** close > prior 20-day high, volume ≥ 1.5× its 20-day average,
  close > 50-DMA > 200-DMA, closed in the top 30% of the day's range, RSI < 75. Stop = breakout level − 0.5×ATR
  (or entry − 1.5×ATR if that's tighter than 1.5%). Target 2.5R. Max hold 15 sessions. Entry up to +1% above the close.
- **Risk and target are measured from the top of the entry range**, so even the worst fill keeps R:R ≥ 1:2 (R-12).
  Risk per share must be 1.5–8% of the price.
- **Quantity (R-05):** min(⌊capital × 1% ÷ risk per share⌋, ⌊capital × 35% ÷ price⌋).
- **Every idea shows:** entry range, stop-loss, target, R:R, quantity, capital used, max loss, charges and the
  break-even move, holding period, confidence, the setup's backtested win rate and average R after costs,
  "Why this idea", "Why not?" and the step-by-step Groww instructions. At most 5 ideas a day; none → **"No trade today."**
- **Backtest proof:** each setup is replayed on all history since 2020 (≥ 5 years) for the whole universe:
  buy at the next open only if inside the entry range; stop checked before target on the same day; gap-downs sell at
  the open; 0.1% slippage; full Groww delivery charges (`rules/costs.yaml`); sizing on your practice capital.
  A setup produces ideas only with **≥ 100 past trades and an average ≥ +0.05R after costs**.
- **Charges vs account size:** because part of Groww's charges is fixed (₹5 minimum brokerage each way, ₹23.6 DP per
  sale), a typical trade at ₹10,000 capital pays ≈ 0.47R in charges, raising the break-even win rate for a 2R target
  from 33% to ≈ 49%. The Trading page shows this table for several capital sizes.

---

## Part E — Known limitations (shown on the Scorecard page)

1. **Survivorship bias:** the Nifty 500 list is today's list. Companies that collapsed and left the index are missing from history, which flatters backtests.
2. **Point-in-time data:** unless the vendor provides "as reported on that date" fundamentals, a backtest of the stock score uses data that wasn't public at the time. Backtests are labelled accordingly. The **forward scorecard** (live recommendations tracked from the day they were made) is the honest measure.
3. **Assumption tables** (C7) are judgement calls. They are editable and versioned.
