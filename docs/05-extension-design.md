# 05 — Chrome Extension: "Decision Sidebar" for Groww (Phase 2)

## 1. What it does

You open a stock or mutual fund page on groww.in and click the NiveshMitra icon. A side panel opens next
to Groww with the app's analysis of that stock or fund, and a warning if buying it would break one of your risk rules.

It never reads anything from the Groww page except the **address in the address bar**
(e.g. `https://groww.in/stocks/tata-consultancy-services-ltd`).

## 2. The guarantee, and how it's enforced

Most extensions ask for broad permissions and *promise* not to misuse them. This one is built so that it
**technically cannot** read your Groww account, because it never receives the permissions that would allow it.

| What it must not do | How that's enforced (not just promised) |
|---|---|
| Read balances, holdings, orders, or anything on the page | **No content scripts** and **no `scripting` permission**. Chrome gives it no way to run code inside Groww pages or read their content |
| Click, fill or submit anything on Groww | Same as above: no code in the page means no clicks |
| Read cookies or login sessions | **No `cookies` permission** and **no host permission for groww.in** |
| Call Groww's servers using your login | **No host permission for groww.in**, plus a Content-Security-Policy with `connect-src` allowing **only** your NiveshMitra backend. The browser itself blocks any other request |
| Watch your browsing | **No `tabs`, `history` or `webNavigation` permission.** The URL is visible only when *you* click the icon (`activeTab`), and only for that tab |
| Use your Google or Groww credentials | It signs in to **your own backend** with a one-time pairing code from the NiveshMitra app (§6) |

### Manifest (complete permission list)

```json
{
  "manifest_version": 3,
  "name": "NiveshMitra Decision Sidebar",
  "version": "0.1.0",
  "description": "Shows your NiveshMitra analysis next to Groww stock and fund pages. Reads only the page address.",
  "permissions": ["activeTab", "sidePanel", "storage", "declarativeContent"],
  "host_permissions": ["http://localhost:8000/*"],
  "background": { "service_worker": "service-worker.js", "type": "module" },
  "action": { "default_title": "NiveshMitra: analyse this page" },
  "side_panel": { "default_path": "sidepanel.html" },
  "content_security_policy": {
    "extension_pages": "script-src 'self'; object-src 'none'; connect-src http://localhost:8000"
  }
}
```

Each permission, and why it's needed:

| Permission | Why | Chrome's install warning |
|---|---|---|
| `activeTab` | Read the current tab's URL **only after you click the icon** | none |
| `sidePanel` | Show the panel next to Groww | none |
| `storage` | Remember the pairing token and your language choice | none |
| `declarativeContent` | Light up the icon only on groww.in stock/fund pages. Chrome evaluates the rule itself; the extension learns nothing | none |
| host `localhost:8000` | Talk to your own backend | "Read and change your data on localhost" |

If the backend moves to the cloud later, `localhost:8000` becomes your own HTTPS domain in both places.
Nothing else changes.

**What's deliberately absent:** `content_scripts`, `scripting`, `cookies`, `tabs`, `history`, `webRequest`,
`webNavigation`, `identity`, `<all_urls>`, and any `groww.in` host permission.

**How you can verify it yourself:** open `chrome://extensions` → NiveshMitra → **Details**.
- **"Site access"** shows no Groww access.
- **"Permissions"** shows only the entries above.
- The extension's source is about 300 lines in `extension/`, readable in one sitting.
- A test (`extension/tests/manifest.test.js`) fails the build if any forbidden permission or key is ever added.

## 3. Data flow

```
 You (on groww.in/stocks/tata-consultancy-services-ltd)
   │ 1. click NiveshMitra icon  (user gesture → Chrome grants activeTab for THIS tab only)
   ▼
 service-worker.js ── chrome.sidePanel.open({tabId})
   │
   ▼
 sidepanel.js
   │ 2. chrome.tabs.query({active:true, currentWindow:true}) → tab.url   (the ONLY Groww-derived data)
   │ 3. parse URL with a fixed pattern:
   │       /stocks/<slug>         → {kind:"stock", slug}
   │       /mutual-funds/<slug>   → {kind:"mf", slug}
   │       anything else          → "Open a Groww stock or fund page"
   │ 4. POST http://localhost:8000/ext/v1/resolve  {kind, slug}
   │       Authorization: Bearer <extension token>          (never a Groww or Google credential)
   ▼
 NiveshMitra backend (your PC)
   │ 5. slug → ISIN / AMFI scheme code  (groww_slug_map; fuzzy name match if new; asks you to pick when unsure)
   │ 6. reads its OWN database: latest score, fair value, flags, your holdings (from Groww API/CAS)
   │ 7. runs a risk "preview" check (doc 04) for a hypothetical buy
   │ 8. returns analysis JSON  → logged in audit_log (slug only)
   ▼
 sidepanel.js renders: score, view, confidence, reasons for/against, red flags,
                       diversification impact, risk warnings, "Open full analysis" link
```

**What leaves your browser:** the kind (`stock`/`mf`) and the URL slug. Nothing else.
**What the backend already knows:** your holdings, which it got through the official read-only Groww API
and your CAS upload, not through the browser.

### Staying in sync as you browse

Groww is a single-page app: moving from one stock to another changes the address without loading a new page.
Chrome keeps the `activeTab` grant while you stay on groww.in. The panel listens to `chrome.tabs.onUpdated` for
**that tab only**, and re-analyses when the slug changes. If you leave groww.in, the grant ends and the panel says
"Click the NiveshMitra icon on a Groww page to analyse it."

## 4. What the panel shows

**Stocks**
- Overall score /100, the view (Buy / Wait for price / Watch / No action / Avoid) and confidence.
- Fair value range and buy range vs the current price.
- Top 3 reasons FOR, top 3 AGAINST, and red flags (pledge, debt, governance, surveillance).
- **Diversification impact:** "Buying ₹10,000 would make IT 31% of your portfolio (limit 25%)."
- Risk-rule result: pass / warning / blocked, with the reason.
- "Explain simply", and a link to the full analysis in the app.

**Mutual funds**
- Rolling 3/5/7-year returns vs category median, and consistency %.
- Risk: volatility, max drawdown, Sortino.
- Expense ratio, Direct vs Regular, and the ₹ cost of Regular over 10 years (warns if you're on a Regular plan page).
- Overlap % with funds you already hold.
- Fit with your goals and risk profile.
- Risk-rule result, and a link to the full analysis.

The panel always shows the footer disclaimer: *"Investments are subject to market risks. Past performance does not
guarantee future returns. Final decisions are yours."*

## 5. Slug resolution

Groww addresses use readable names (`hdfc-bank-ltd`), not NSE symbols. The backend:
1. Looks the slug up in `groww_slug_map`.
2. If it's new, normalises it (drops `-ltd`, `-limited`, `-direct-growth`, …) and fuzzy-matches against `instruments.name` and `mf_schemes.name`.
3. Confidence ≥ 0.92 → uses the match. Otherwise the panel shows the top 3 candidates for you to pick once, and remembers your choice (`confirmed_by_user = 1`).

The URL patterns live in `extension/src/patterns.js`, so if Groww changes its URL structure, only that one file needs updating.

## 6. Authentication to your backend (pairing)

1. In the NiveshMitra app: **Settings → Chrome extension → Pair**. The app shows a 6-digit code, valid for 5 minutes, usable once.
2. Type the code in the side panel. The backend swaps it for an **extension token** with:
   - scope `ext:read`, which only allows the `/ext/v1/*` analysis endpoints: no settings, no secrets, no raw holdings export;
   - a 30-day expiry;
   - revocation any time from Settings.
3. The token is kept in `chrome.storage.local` (extension-only storage, which websites can't reach). Only a hash is stored in the backend.

## 7. Backend endpoints (extension scope only)

| Method | Path | Returns |
|---|---|---|
| POST | `/ext/v1/pair` | Exchange a pairing code for a token |
| POST | `/ext/v1/resolve` | `{kind, slug}` → matched instrument or candidate list |
| GET | `/ext/v1/stock/{isin}` | Stock analysis + portfolio impact + risk preview |
| GET | `/ext/v1/fund/{scheme_code}` | Fund analysis + overlap + goal fit + risk preview |
| POST | `/ext/v1/confirm-slug` | Save your pick for an ambiguous slug |

## 8. Failure behaviour

| Situation | Panel shows |
|---|---|
| Backend not running | "NiveshMitra isn't running on this PC. Start it and click Retry." |
| Data stale (rule R-13) | "Data unavailable — last updated 2 days ago. No recommendation shown." |
| Token expired or revoked | "Pair again from NiveshMitra Settings." |
| Not a stock or fund page | "Open a Groww stock or mutual fund page." |
