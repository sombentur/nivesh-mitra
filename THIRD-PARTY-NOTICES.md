# Third-party software, fonts and data

Nivesh Mitra itself is released under the MIT licence (see LICENSE). It depends on the software below, which is
downloaded by the setup script from the public package registries (PyPI, npm, Google Fonts) and is **not** included in
this repository. Each item keeps its own licence. Versions are the ones pinned in `backend/uv.lock` and
`web/package-lock.json` at the time of writing.

## Python packages (backend)

| Package | Version | Licence | Used for |
|---|---|---|---|
| fastapi | 0.142 | MIT | HTTP API |
| uvicorn | 0.54 | BSD-3-Clause | ASGI server |
| sqlalchemy | 2.1 | MIT | Database access |
| alembic | 1.20 | MIT | Database migrations |
| pydantic | 2.13 | MIT | Data validation |
| pydantic-settings | 2.15 | MIT | Configuration from environment / `.env` |
| cryptography | 50 | Apache-2.0 OR BSD-3-Clause | Encrypting stored keys (Fernet) |
| keyring | 25 | MIT | Master key in Windows Credential Manager |
| pyotp | 2.10 | MIT | Authenticator (TOTP) codes |
| segno | 1.6 | BSD-3-Clause | QR code for the authenticator |
| google-auth | 2.59 | Apache-2.0 | Verifying Google sign-in tokens |
| requests | 2.34 | Apache-2.0 | HTTP client |
| httpx | 0.28 | BSD-3-Clause | HTTP client |
| python-multipart | 0.0.32 | Apache-2.0 | Form parsing |
| pandas | 2.3 | BSD-3-Clause | Price and NAV calculations |
| numpy | 2.5 | BSD-3-Clause (with 0BSD/MIT/Zlib/CC0 parts) | Numerics |
| pyyaml | 6.0 | MIT | Rule files |
| python-dateutil | 2.9 | Apache-2.0 / BSD-3-Clause (dual) | Dates |
| apscheduler | 3.11 | MIT | Scheduled jobs |
| growwapi | 1.5.0 | MIT (© Groww) | Groww Trade API SDK, used read-only; order methods are blocked by the app |
| mcp | 2.2 | MIT | Model Context Protocol client (Trendlyne) |
| anthropic | 1.9 | MIT | Claude API client (optional feature) |
| pytest | 9.1 | MIT | Tests (development only) |

Transitive dependencies (packages these packages need) are listed with their licences in `backend/uv.lock` metadata and
are all under permissive open-source licences as installed.

## JavaScript packages (web app)

| Package | Version | Licence |
|---|---|---|
| next | 16.3.7 | MIT |
| react, react-dom | 19.2.8 | MIT |
| tailwindcss, @tailwindcss/postcss | 4.3 | MIT |
| typescript | 5.9 | Apache-2.0 |
| eslint, eslint-config-next | 9.39 / 16.3.7 | MIT |
| @types/node, @types/react, @types/react-dom | — | MIT |

## Fonts

Loaded through `next/font/google` at build time (not stored in the repository):

| Font | Licence |
|---|---|
| Inter (Rasmus Andersson) | SIL Open Font License 1.1 |
| Outfit (Rodrigo Fuenzalida) | SIL Open Font License 1.1 |
| Geist Mono (Vercel) | SIL Open Font License 1.1 |

## Images and icons

- The Nivesh Mitra logo and icons in `web/public/brand/` belong to this project's author.
- All other icons are small inline SVGs drawn for this project (`web/src/components/icons.tsx`).
- The "Sign in with Google" button is rendered at run time by Google Identity Services under Google's branding
  guidelines; no Google artwork is stored here.
- The sample SVGs that `create-next-app` adds to a new project were removed.

## Data sources and services (fetched at run time, through your own accounts)

None of this data is included in the repository. Each provider's terms apply to you as the user.

| Source | What | Terms to note |
|---|---|---|
| AMFI (amfiindia.com) | Daily mutual-fund NAVs; scheme expense ratios (TER) and AUM | Published by AMFI for public use; please respect their site's terms |
| mfapi.in | Historical NAV series per scheme | Free public API; be considerate with request volume |
| Groww Trade API (growwapi SDK) | Holdings (read-only), live quotes, daily and 15-minute price history | Needs your own Groww account and paid Trade API plan; Groww's API terms apply |
| Trendlyne MCP | Headlines, corporate events and, later, red-flag data | Needs your own Trendlyne MCP subscription (individual use). Trendlyne's Terms of Use restrict storing their data in a database; the app keeps only a short cache and derived flags — see `docs/06-fundamentals-vendor.md` |
| Anthropic Claude API | Optional rewording of explanations and news tone | Needs your own API key; Anthropic's usage policies apply |
| Google Identity Services | Sign-in | Needs a Google Cloud OAuth Client ID that you create |
| NSE / BSE | Exchange holiday dates typed into `backend/app/rules/market_holidays.yaml` | Public facts; nothing is downloaded from the exchanges' websites |
| SEBI | Statistics quoted in the "reality check" step, with their source and date | Public facts |

Groww, Trendlyne, AMFI, NSE, BSE, SEBI, Google and Claude are trademarks or names of their respective owners. This
project is independent and not affiliated with, sponsored by or endorsed by any of them.
