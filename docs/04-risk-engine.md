# 04 — Risk-Management Rule Engine

## 1. Purpose

The risk engine is a gate that **every** suggestion passes through before you see it. It also checks
anything you log or preview (a manual trade, a stock opened in the Chrome sidebar, a settings change).
It protects capital first. No rule can be skipped silently.

## 2. Where it runs

```
                 ┌──────────────────────────────┐
 Stock engine ──►│                              │──► Recommendation shown (possibly with qty reduced)
 MF engine ─────►│        RISK ENGINE           │──► Recommendation blocked (reason shown)
 Swing engine ──►│  evaluate(context) → result  │──► Warning that needs typed acknowledgement
 Sidebar preview►│                              │
 Manual trade ──►│                              │──► Logged in risk_checks (always)
 Settings edit ─►└──────────────────────────────┘
```

## 3. Design

```python
class Severity(Enum):
    INFO = "info"          # shown, no action needed
    WARN = "warn"          # shown; to proceed you type a reason → logged in risk_overrides
    BLOCK = "block"        # suggestion removed / action refused; cannot be overridden

@dataclass
class ProposedAction:
    kind: Literal["buy_stock", "sell_stock", "start_sip", "lumpsum_mf", "redeem_mf", "trade_idea"]
    instrument_id: int | None
    scheme_code: str | None
    bucket: Literal["core", "satellite", "trading"]
    qty: Decimal | None
    price: Decimal | None
    amount: Decimal | None
    stop_loss: Decimal | None
    target: Decimal | None
    segment: str            # "CASH" or "MF" — anything else is BLOCKed by R-01
    product: str            # "DELIVERY" — anything else is BLOCKed by R-02

@dataclass
class RiskContext:
    action: ProposedAction
    portfolio: PortfolioSnapshot      # holdings, sector weights, bucket values
    profile: RiskProfile               # category, emergency-fund months, horizon, experience
    day_state: TradingDayState         # today's realised P&L, consecutive losses, cooling-off
    data_health: DataHealth            # freshness of each data source
    settings: RiskSettings             # current (effective) parameters

@dataclass
class Finding:
    rule_code: str
    severity: Severity
    message_simple: str                # beginner wording, EN (KN in Phase 2)
    numbers: dict                      # the exact figures behind the message
    suggested_fix: str | None          # e.g. "Reduce to 12 shares"

@dataclass
class RiskResult:
    overall: Literal["pass", "warn", "block"]
    findings: list[Finding]
    adjusted_qty: Decimal | None       # engine may shrink quantity instead of blocking
```

- Each rule is a small class with `evaluate(ctx) -> list[Finding]`. Rules are **pure functions**, so they are easy to unit-test.
- The engine runs all enabled rules, applies quantity adjustments (R-05 first), and sets `overall` to the most severe finding.
- The whole result is saved to `risk_checks` (doc 02).
- Rule definitions and default parameters are seeded from `backend/app/rules/risk_rules.yaml` into the `risk_rules` table.

## 4. The rules

| Code | Rule | Default parameters | Severity | Overridable? |
|---|---|---|---|---|
| **R-01** | No derivatives (F&O) — only cash-segment equity and mutual funds | — | BLOCK | **Never** |
| **R-02** | No margin, MTF or intraday product — Delivery only | — | BLOCK | **Never** |
| **R-03** | No penny stocks | price < ₹20 or mcap < ₹1,000 cr | BLOCK | **Never** (beginner profiles) |
| **R-04** | Liquidity | median traded value < ₹5 cr | BLOCK for trades, WARN for long-term | WARN only |
| **R-05** | Max loss per trade (position sizing) | 1% of trading capital (range 0.5–2%) | Adjusts qty; BLOCK if even 1 share breaks it | No |
| **R-06** | Daily loss limit — no new trade ideas for the rest of the day | 3% of trading capital (range 1–5%) | BLOCK | **Never** |
| **R-07** | Single stock ≤ 10% of total portfolio (after this buy) | 10% | WARN | Yes, with typed reason |
| **R-08** | Sector ≤ 25% of total portfolio (after this buy) | 25% | WARN | Yes, with typed reason |
| **R-09** | Trading bucket cap | 10% of investable money | BLOCK new trades once reached | No |
| **R-10** | Cooling-off after losing streak | 3 losses in a row → 2 trading days off; 5 of last 8 → 5 days | BLOCK trade ideas | **Never** |
| **R-11** | Emergency fund first | < 6 months → WARN on non-liquid buys; < 3 months → BLOCK trade ideas | WARN / BLOCK | WARN only |
| **R-12** | Minimum reward : risk | (target − entry) ÷ (entry − stop) ≥ 2.0 | BLOCK the idea | No |
| **R-13** | Stale data | price older than 15 min in market hours / NAV older than 1 business day / fundamentals older than 120 days | BLOCK recommendation → "Data unavailable" | **Never** |
| **R-14** | Red-flag stock | pledge > 0, ASM/GSM, audit flags (doc 03 §B2, §B6) | E-codes BLOCK; flags WARN | WARN only |
| **R-15** | Paper-trading period | first 60 days: trade ideas are paper-only; real-money long-term buys show a banner | INFO / BLOCK real trades | Ends after the 60-day review |
| **R-16** | SIP budget | total SIPs > monthly investable amount | WARN | Yes |
| **R-17** | Goal horizon mismatch | equity for a goal < 3 years away (equity > the cap in doc 03 §C6) | WARN | Yes |
| **R-18** | Short-term tax awareness | selling equity held < 12 months at a gain; or 12-month mark within 30 days | INFO ("Waiting N days changes tax from 20% to 12.5%") | n/a |
| **R-19** | Exit load awareness | redeeming within the fund's exit-load period | INFO with ₹ amount | n/a |

## 5. Position sizing (R-05)

```
risk_per_share   = entry − stop_loss
max_risk_rupees  = trading_capital × max_risk_pct            (default 1%)
qty_by_risk      = floor(max_risk_rupees / risk_per_share)
qty_by_bucket    = floor(0.25 × trading_capital / entry)      (no single trade > 25% of trading bucket)
qty_by_R07       = floor((0.10 × total_portfolio − current_value_of_stock) / entry)
qty              = min(qty_by_risk, qty_by_bucket, qty_by_R07)
if qty < 1 → BLOCK "This trade is too risky for your trading capital."
```

Example: trading capital ₹10,000, entry ₹500, stop ₹480.
- max risk = ₹100, risk per share = ₹20 → qty_by_risk = **5 shares**.
- qty_by_bucket = floor(2,500 ÷ 500) = 5.
- **Result: 5 shares.** Worst case, you lose ₹100 plus costs.

## 6. "Cannot be silently bypassed"

1. **BLOCK** findings have no override button. The UI explains why and offers the nearest safe alternative (smaller quantity, an index fund instead, "no trade today").
2. **WARN** findings need you to **type a reason** (at least 10 characters). The reason is stored in `risk_overrides`, linked to the check.
3. The **Scorecard** has an "Overrides" section: how many times you overrode each rule, and what happened afterwards.
4. **Changing risk parameters:**
   - **Tightening** (e.g. max risk 1% → 0.5%) takes effect **immediately**.
   - **Loosening** (e.g. trading cap 10% → 15%) takes effect after a **24-hour delay** and needs a typed reason, so you can't loosen a rule in the heat of a losing day.
   - Values outside the allowed ranges in §4 are rejected.
   - Every change is written to `audit_log`.
5. Rules R-01, R-02, R-03, R-06, R-10 and R-13 cannot be disabled in Settings.

## 7. Daily state machine (trading bucket)

```
            new trading day (09:00 IST)
                     │
                     ▼
               ┌──────────┐   realised + open loss ≥ daily limit    ┌──────────────┐
               │  ACTIVE  │ ───────────────────────────────────────►│ LIMIT_HIT    │
               └──────────┘                                          │ (no ideas    │
                     │  3 consecutive losing trades logged           │  until next  │
                     ▼                                               │  trading day)│
               ┌──────────────┐                                      └──────────────┘
               │ COOLING_OFF  │  lasts 2 (or 5) trading days, then → ACTIVE
               └──────────────┘
```

State lives in `trading_day_state` (doc 02). Because you trade manually, you **log** each closed trade
(or the Groww holdings sync detects it). The engine only knows about losses it is told about. The UI reminds you
to log closed trades in the evening summary.

## 8. First-run SEBI reality check

Shown once during onboarding, and again whenever you open the trading bucket for the first time.
You must tick "I have read this" to continue. The figures are stored in config with their source and date, so they can be updated when SEBI publishes a new study.

> **What SEBI found about individual traders**
> - **F&O:** 87.7% of individual traders lost money in FY26 (90.9% in FY25). The average loss was about ₹1.17 lakh per person.
>   *(SEBI study, press release 50/2026, August 2026)*
> - **Intraday (cash segment):** over 70% of individual intraday traders made losses in FY23, and 80% of those who traded more
>   than 500 times a year. *(SEBI study, July 2024)*
>
> This is why NiveshMitra never suggests F&O or intraday trades, and why short-term ideas are small, capped, and paper-only for your first 60 days.

## 9. Testing

- One unit-test file per rule, with boundary cases (exactly 10.00%, 10.01%, and so on).
- A property test checks that `overall` is never "pass" when any finding is BLOCK.
- A "read-only guard" test checks that no module anywhere references an order-placement function (see doc 01, §5).
