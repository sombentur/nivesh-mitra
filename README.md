# Nivesh Mitra

<p align="center"><img src="web/public/brand/logo.png" alt="Nivesh Mitra" width="340"></p>

**A personal, decision-only investment assistant for Indian mutual funds and stocks.**
It runs on your own Windows PC, reads market data through your own accounts, and tells you in plain language what it
would do and why — including "do nothing today". It **never places orders**: you make every purchase yourself in your
broker's app.

> **For personal education only. Not investment advice. Does not place orders.**
> Investments are subject to market risks. Past performance does not guarantee future returns.
> Nivesh Mitra is not a SEBI-registered investment adviser. See [DISCLAIMER.md](DISCLAIMER.md).

Built with AI-assisted development (Claude).

---

## Who it is for

One person, on one PC: an individual investor in India — especially a beginner — who wants a calm, honest second
opinion about mutual funds and stocks, with every number explained and nothing hidden. It is not a trading terminal,
not a tip service, and not for firms or advisers.

## What it does

| Area | What you get |
|---|---|
| **Dashboard** | Greeting with today's decisions; a Yesterday · Today · Tomorrow row (trading days only); separate scrolling NSE and BSE tapes (live during market hours); 8 index cards with sparklines; market breadth and a sector heat-map; stock snapshots (trend leaders, gainers, losers, most active, 52-week highs); Nifty 50 chart and "market mood"; news pulse; the best-scored fund for 3 months to 5+ years with **Buy on Groww** links; a trading calendar (month or week) |
| **Sectors** | Click any sector tile to see that sector's NSE index (chart, 1w / 1m / 3m) and the tracked companies in it, grouped by industry |
| **Mutual funds** | Every active fund from AMFI's daily data; scores (0–100) that compare a fund only with funds of the same kind — rolling returns in good and bad years, steadiness, cost; fund pages with up to 10+ years of NAV history; Direct-vs-Regular cost warnings |
| **My plan** | Emergency fund first, then a SIP per goal using the best-scored Direct funds, affordable amounts, Groww steps, and a SIP calculator with cautious / normal / good scenarios |
| **My profile** | A 10-question risk profile, a suggested split (mutual funds / long-term stocks / short-term trading), goals with inflation, and safety rules you cannot loosen in a hurry (a 24-hour delay) |
| **Trading (practice)** | A pretend-money account; swing setups backtested on 5+ years of prices with the broker's full charges and slippage; intraday setups judged only on data they were never tuned on; a daily practice plan and scoreboard. **A setup that loses money after charges is switched OFF and never produces ideas** |
| **Explanations** | Plain-language templates, or (optionally) Claude rewording the same facts. Numbers always come from the rule engine, never from the AI |
| **Looks** | Navy-and-emerald design, light and dark themes, phone-friendly, reduced-motion aware |

## How it stays safe and honest

- **Read-only broker access.** The Groww SDK's order functions are blocked in code; a test fails if any of them becomes reachable. The app cannot buy, sell, modify or cancel anything.
- **Your keys stay on your PC, encrypted.** API keys are stored encrypted in a local database; the encryption key lives in Windows Credential Manager. The app never asks for your Google or Groww password.
- **Local only.** The app listens on `127.0.0.1`. Nothing on your Wi-Fi can reach it, and nothing is uploaded anywhere.
- **Two-step sign-in.** Google sign-in (with your own Google Client ID) plus a code from an authenticator app. Only one email address — yours — is ever allowed in.
- **No scraping.** Data comes only from official APIs and published files (AMFI, mfapi.in, Groww Trade API, Trendlyne MCP).
- **Honest by design.** Ranges and confidence on every idea; "do nothing" is a valid answer; losing strategies are switched off; past results are labelled as past results.

## Requirements

| Needed | Notes |
|---|---|
| **Windows 10 or 11** | The setup scripts, the Credential Manager key store and all testing are Windows-only (see Known limits) |
| **Python 3** from python.org | Any recent version with the `py` launcher. Setup downloads its own private Python 3.12 |
| **Node.js 20 LTS or newer** | From nodejs.org |
| **A Google account** | For sign-in. You create a free "Client ID" in Google Cloud (the app shows the steps; about 5 minutes) |
| **An authenticator app** on your phone | Google Authenticator or Microsoft Authenticator |
| **Groww Trade API** (paid plan) | For stock prices, indices, the tapes and trading research. Without it the mutual-fund side still works fully |
| Optional: **Trendlyne MCP** subscription | News pulse (headlines) and, later, red-flag checks |
| Optional: **Claude API key** | Friendlier explanations and news tone; a monthly spending cap is enforced |

About 1 GB of disk space after setup; a few hundred MB are downloaded the first time.

## Install

The short version — the full, click-by-click guide is in **[INSTALL.md](INSTALL.md)**.

1. Install Python and Node.js (links above).
2. Download this project (**Code → Download ZIP** on GitHub) and unzip it to a folder of your choice.
3. Double-click **`Setup NiveshMitra.bat`** and wait for "Setup complete".
4. Double-click **`Start NiveshMitra.bat`**. Your browser opens **http://localhost:3000**.
5. Follow the on-screen first-time setup (Google Client ID → sign in → authenticator → 10 questions).
6. In **Settings**, paste the keys you have (Groww, Trendlyne, Claude). Data downloads start by themselves.

## Everything you enter yourself (nothing is built in)

| Where | What | Why |
|---|---|---|
| First-time setup screen | Google Client ID and your Google email | Sign-in. Only that email can ever sign in |
| Settings → Connections | Groww API key (TOTP token) and TOTP secret | Read-only holdings, prices, practice trading |
| Settings → Connections | Trendlyne MCP server URL | News pulse and red-flag checks |
| Settings → Connections | Claude API key (and workspace ID if your key needs it) | Optional explanations; spending capped monthly |
| Settings → Connections | EODHD API key | Optional fundamentals vendor (later build step) |
| `.env` (optional, advanced) | Ports, data folder, scheduler on/off | See [.env.example](.env.example) |

The app ships with **no keys, no accounts and no personal data**. Settings only ever show the last 4 characters of a key.

## Where your data lives

| What | Where |
|---|---|
| Database (profile, goals, settings, prices, scores, practice trades) | `data\niveshmitra.db` |
| Automatic backups | `data\backups\` (nightly and before every upgrade; last 7 kept) |
| 15-minute stock prices | `data\intraday\` (large; downloaded again automatically if deleted) |
| Encryption key | Windows Credential Manager → entry "NiveshMitra" |

The `data` folder is personal. Never share it, upload it or commit it (the `.gitignore` blocks it).

## Known limits

- **Windows only** (tested on Windows 11). The code is mostly portable, but the launcher scripts and key store are Windows-specific.
- **Market data needs Groww's paid Trade API plan.** The free trial excludes prices and history. Groww's SDK marks the price-history feed as deprecated; if Groww retires it, price updates stop with a clear error until the connector is updated.
- **Market holidays** for the current year are in `backend\app\rules\market_holidays.yaml`. Each December, add next year's NSE/BSE list (the file explains the format); until then, weekdays of the new year show as trading days.
- The **sector pages** group companies by their main business from a hand-maintained list (`backend\app\rules\sectors.yaml`), not NSE's official index membership. A tracked company that is missing from the list is named on the Sectors page so it can be added.
- **Practice only.** None of the built-in short-term strategies made money after charges in testing, so they are switched off and shown as practice. This is a feature, not a bug.
- Not yet built: mutual-fund statement (CAS) import, the long-term stock engine with fundamentals, the recommendation scorecard, the morning brief, Kannada translations.
- One user per installation. No mobile app (the web app works on a phone browser on the same PC only, because it listens on `127.0.0.1`).

## For developers

```
backend/   FastAPI + SQLAlchemy + Alembic (SQLite), APScheduler jobs, rule files in app/rules/*.yaml, pytest suite
web/       Next.js 16 (App Router) + Tailwind CSS 4; /api/* is proxied to the backend
setup/     PowerShell scripts behind the .bat launchers
docs/      Design documents: architecture, database, scoring formulas, risk rules, extension design, data vendors
```

- Backend tests: `uv --directory backend run pytest -q` (they use a temporary database and never touch `data\`).
- Web checks: `npm --prefix web run lint` and `npx --prefix web tsc --noEmit`.
- Development servers: `uv --directory backend run uvicorn app.main:app --reload` and `npm --prefix web run dev`.
- Environment variables: see [.env.example](.env.example). Every key or account the app needs is entered in the app itself.

## Third-party software and data

Every library, font and data source, with its licence or terms, is listed in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Market data is fetched at run time through **your own** accounts and
is subject to each provider's terms; none of it is included in this repository.

## Credits and licence

- Author: [@sombentur](https://github.com/sombentur)
- Built with AI-assisted development (Claude).
- Licence: [MIT](LICENSE). "Groww", "Trendlyne", "AMFI", "NSE", "BSE" and "Claude" are names of their respective owners; this project is not affiliated with or endorsed by any of them.
