# NiveshMitra — Design Documents

| # | Document | What it answers |
|---|---|---|
| 01 | [Architecture](01-architecture.md) | How the pieces fit, the daily schedule, how Groww stays read-only, how the AI layer is kept honest, verified facts |
| 02 | [Database schema](02-database-schema.md) | Every table, and why losing recommendations can't be deleted |
| 03 | [Scoring formulas](03-scoring-formulas.md) | Risk profile, stock score, mutual fund score, SIP maths — with every weight |
| 04 | [Risk rule engine](04-risk-engine.md) | The 19 rules, position sizing, and why no rule can be skipped silently |
| 05 | [Chrome extension](05-extension-design.md) | Permission list and data flow showing it can't touch your Groww account |
| 06 | [Fundamentals vendor](06-fundamentals-vendor.md) | Which paid data provider to use, and what it costs |

## Design decisions (30-Sep-2026)

- Runs locally on your Windows PC, with a SQLite database (ready to move to Postgres later).
- Groww Trade API subscription, used **read-only**.
- Company fundamentals from a **paid vendor**, with **manual file upload** as a selectable backup.
- Explanations: **Claude API** or **manual templates**, switchable in Settings; templates are the automatic fallback.
- Mutual fund statements: download your CAS from **CAMS or KFintech** (the parser doesn't support MF Central statements).
