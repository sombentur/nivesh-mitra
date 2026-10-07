# 06 — Fundamentals Data: Vendor Choice and Costs

Checked 30-Sep-2026. Prices change, so confirm on the vendor's page before paying.

## 1. What the stock engine needs

| Data | Used for | Where it comes from |
|---|---|---|
| Annual + quarterly P&L, balance sheet, cash flow (5+ yrs) | Quality, growth, strength, EPS, FCF | **Vendor** (or manual upload) |
| Daily prices (5+ yrs) | P/E history, valuation, returns | **Groww API** (your Trade API plan) |
| Promoter holding + pledge % | Ownership pillar, red flags, exclusion E6 | **NSE pledged-data CSV** — free, you download it quarterly |
| FII / DII holding trend | Ownership pillar (3 of 100 points) | Optional. If missing, the weight is rescaled (doc 03 §B4) |
| Nifty 500 list + sectors | Universe, peer groups | **niftyindices.com CSV** — free, you download it twice a year |
| Surveillance (ASM/GSM), auditor resignations, qualified opinions | Exclusions E4/E5 | Phase 1: a "flag this stock" form + NSE surveillance CSV upload. Phase 2: exchange announcements via news feed |

Ratios such as ROE, ROCE, D/E, P/E, PEG and interest coverage are **calculated by NiveshMitra** from the raw statements and Groww prices,
so every vendor is treated the same and the formulas stay transparent.

Only half the balance-sheet/cash-flow periods are real: Indian companies publish balance sheets and cash flows half-yearly, not quarterly.
Consolidated figures are used where available, standalone otherwise, and the card says which.

## 2. Options compared

| Vendor | Price (cheapest India-fundamentals plan) | Good | Concerns | Verdict |
|---|---|---|---|---|
| **EODHD** — "Equity Analyst" | **US$59.99/mo** (≈ ₹5,000–5,500), month-to-month; annual = 2 months free | Licensed vendor with explicit **personal-use** plans; long history for large companies (~6 yrs / 20 quarters minimum for smaller ones); official Python SDK; a full Nifty 500 refresh uses ~5% of one day's quota | Global vendor: Indian mapping (standalone vs consolidated, fiscal-year labels) needs spot checks. No shareholding or pledge data | ✅ **Recommended primary** |
| **stockinsights.ai** — India Developer | ₹5,000/mo, 10k calls/mo, 7-day free trial | Built from exchange filings; consolidated/standalone switch; bank and insurance templates; promoter/FII/DII history | No pledge, ratios or valuation endpoints; history depth unverified | Good alternative, or an add-on if you want FII/DII data |
| **Finnhub** — Fundamental-1 | US$50/mo per market, billed quarterly | 10 yrs / 40 quarters of standardised statements; personal-use licence | Indian data quality unverified; quarterly billing | Possible, less proven for India |
| **FMP** — Ultimate | US$139/mo (US$99 annual) | Ratios included | India only on its top tier; expensive | ❌ Too costly |
| **IndianAPI.in** | ₹399–1,799/mo | Cheapest; India-specific fields | Doesn't disclose its data source, and its layout mirrors Screener.in (likely scraped) → conflicts with your "only legitimate sources" rule | ❌ Not recommended |
| **Screener.in, Tickertape, Tijori** | No public API | — | Scraping breaches their terms. Screener's own **Export to Excel** (done by you) is fine → that's the **manual upload** mode | Manual mode only |
| **ACE Equity, CMOTS, Accord** | ~₹1.25 lakh/yr and up (enterprise) | Complete, licensed | Priced for businesses | ❌ Overkill |

### Trendlyne MCP (optional subscription)

Checked 30-Sep-2026 from Trendlyne's documentation bundle and help articles.

| | |
|---|---|
| Tools | `search_entities`, `get_parameter_values_multi_stock` (natural-language query over Trendlyne's database), `get_overview_news_corp_events` (overview incl. **ASM/GSM status** and **DVM scores**, technicals, news + **exchange announcements**, corporate events), `get_ownership_deals_insider_sast` (latest **shareholding**, **SAST/insider trades and share pledges**, bulk/block deals), `get_document_search_results` (annual reports, results, concall transcripts), watchlist tools |
| Identifier | NSE symbol (e.g. `INFY`), BSE code or ISIN |
| Access | Personal server URL with a token inside it (`https://mcp.trendlyne.com/mcp/?token=…`) → stored encrypted like any other key |
| Quota | Pro ₹299/mo: 400 calls/day, **2,000/month**. Max ₹499/mo: 1,000/day, 10,000/month |
| Strengths | Exactly the India-specific data EODHD lacks: pledge, surveillance, insider trades, block deals, announcements, board meetings, DVM |
| Limits | Mostly **latest values** (the catalogue shows annual history back ~5 years and quarterly ~8 quarters, not confirmed through MCP). No price time series. No mutual fund data |
| Terms | "Pro and Max plans are for individual use only" ✓ fits. But the Terms of Use (§6) say you may not *"use the information in a searchable, machine-readable database unless separately and specifically authorized in writing"* — so a local database of Trendlyne data needs Trendlyne's written OK |

### Update 30-Sep-2026 — checked against a live MCP server

A live Trendlyne MCP server offers **12 tools**. Two are newer than the documentation reviewed above:

- `search_financial_parameters` turns a plain name ("ROE annual", "PE TTM", "promoter pledge") into Trendlyne's parameter token.
- `get_stock_parameter_values` returns up to **50 parameters for up to 10 stocks in one call**, current values and the screener's
  fixed look-backs (e.g. "net profit 5 years ago"). A Nifty 500 fundamentals snapshot is therefore about **50 calls**, well inside the
  Pro plan's 2,000 a month.
- It has **no date parameter**, so it cannot supply daily price history. Trading ideas and backtests keep using Groww candles.

Implication: Trendlyne can likely cover most of the long-term stock engine's fundamentals (ratios, growth, valuation, ownership,
pledge, surveillance), making EODHD optional. This depends on Trendlyne's written OK to keep the numbers locally (§5). Until then,
scores are computed from an in-memory fetch and only the derived score and red flags are kept.

Trendlyne's website subscriptions are separate from MCP and can't be read by apps; their "Data Downloader" produces
screener exports you download by hand, which could feed the manual-upload mode.

## 3. Recommendation — best-quality setup

For the best decisions, each source does what it's best at:

| Job | Source |
|---|---|
| 5+ years of statements for scoring all Nifty 500 stocks (stored locally) | **EODHD "Equity Analyst"** — licensed, personal plan, storage allowed for personal use |
| Red flags and "what changed": pledge, ASM/GSM, insider/SAST trades, bulk/block deals, announcements, board meetings, latest shareholding | **Trendlyne MCP** — queried **on demand** for stocks you hold, your watchlist, the current shortlist, and any stock you open. Results are held in a short cache (default 24 h) and then discarded; only the derived flag ("pledge 12%, source Trendlyne, 30-Sep") is kept on the recommendation record |
| Sanity check of vendor numbers | **Trendlyne** latest ROE/ROCE/P/E compared with EODHD-derived values for the shortlist. A mismatch > 10% lowers confidence and is shown |
| Backup / stocks not covered | **Manual upload** (Screener "Export to Excel", NSE pledged-data CSV) |

**Call budget on the Pro plan (2,000/month):** holdings (~10 stocks) + watchlist (~15) + shortlist (~25), checked weekly with 2 calls each ≈ 400 calls/month.
Stocks you open on demand add 2 calls each (one call per stock per day, since results are cached).
The budget meter in Settings stops scheduled checks at 80% of the monthly cap, keeping the rest for stocks you open.

**Written permission (recommended):** email contact@trendlyne.com asking whether a single-user personal app may keep Trendlyne MCP results
in a private local database. A draft is in §5. If they agree in writing, the 24-hour cache limit can be lifted, and Trendlyne can also supply
history, cutting the EODHD dependency.

First month: the app runs a **cross-check report** comparing EODHD's figures for ~20 companies with their published results and Trendlyne's values.
Each vendor sits behind the same adapter, so switching vendor is a Settings change, not a code change.

**Nobody needs to subscribe to EODHD yet.** Fundamentals are step 7 of the build.

## 4. Running cost — please read

| Item | Monthly |
|---|---|
| Groww Trade API | ₹589 (₹499 + GST) |
| Trendlyne MCP | ₹299 Pro / ₹499 Max (optional) |
| EODHD Equity Analyst | ≈ ₹5,000–5,500 |
| Claude API (explanations) | Usually a few hundred ₹; hard cap in Settings (default ₹500) |
| **Total** | **≈ ₹6,000–6,500 / month** |

Compare this with how much you invest each month. At ₹25,000/month, data costs would be about a quarter of your investment,
which no stock-picking edge is likely to make up. The **mutual fund side** (65–90% of your money under every profile) needs **no paid
data at all**: AMFI, mfapi.in and your CAS are free. Only the direct-stock part needs the vendor.

Cheaper ways to run it:
1. **Start free:** MF engine + manual stock uploads for a shortlist you care about. Add EODHD later when you want whole-market screening.
2. **Pay annually** once you've decided to keep it (EODHD annual = 2 months free).
3. **Pause EODHD** in months you're not actively adding stocks. Scores freeze and are marked "fundamentals as of <date>".

## 5. Draft email to Trendlyne (you send it; nothing is sent automatically)

> **To:** contact@trendlyne.com
> **Subject:** Trendlyne MCP — personal-use question about local caching
>
> Hello Trendlyne team,
>
> I'm a Trendlyne MCP subscriber (account: <your email>). I've built a personal, single-user investment notebook on my own PC.
> It calls my Trendlyne MCP server URL from a small Python program, instead of a chat app, to check stocks I hold or am considering
> (pledge, ASM/GSM status, insider trades, announcements, shareholding).
>
> 1. Is calling the MCP server from my own script, within my plan's call limits, allowed under the individual-use plan?
> 2. May I keep the results in a private database on my own computer (never shared, published or redistributed) so I don't
>    re-query the same data? If so, is there a retention limit?
>
> Thank you,
> <your name>
