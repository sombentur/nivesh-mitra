# Installing Nivesh Mitra — step by step

This guide assumes nothing: if you can download a file and double-click it, you can do this. Budget about **30 minutes**,
most of it waiting for downloads. You need a Windows 10 or 11 PC with an internet connection.

> Nivesh Mitra is for personal education only. It is not investment advice and it never places orders.

## Part 1 — Install the two free tools it runs on

### 1. Python

1. Open https://www.python.org/downloads/ and click the big **Download Python 3.x** button.
2. Run the downloaded file. On the first screen **tick "Add python.exe to PATH"**, then click **Install Now**.
3. When it says "Setup was successful", close it.

(Nivesh Mitra downloads its own private copy of Python 3.12 during setup, so the exact version you install here
doesn't matter — it only needs the `py` launcher that comes with it.)

### 2. Node.js

1. Open https://nodejs.org/ and download the **LTS** version (the one recommended "for most users").
2. Run the installer and keep clicking **Next** with the default choices, then **Install**, then **Finish**.

If either tool was already installed, skip that step. Node.js must be version 20 or newer; setup checks this.

## Part 2 — Get Nivesh Mitra onto your PC

1. On the project's GitHub page click the green **Code** button → **Download ZIP**.
2. Find the downloaded zip in your **Downloads** folder, right-click it → **Extract All…**.
3. Choose where to keep the app, for example `C:\NiveshMitra` or a folder in your Documents. Avoid folders that sync to the
   cloud (OneDrive, Google Drive) — the app's database changes every day and syncing it is slow and risky.
4. Open the extracted folder. You should see `Setup NiveshMitra.bat`, `Start NiveshMitra.bat`, `Stop NiveshMitra.bat`,
   and folders called `backend`, `web`, `docs` and `setup`.

## Part 3 — One-time setup (5–10 minutes, mostly waiting)

1. Double-click **`Setup NiveshMitra.bat`**.
2. If Windows shows a blue "Windows protected your PC" box, click **More info → Run anyway**. (The script is plain
   PowerShell that you can read in the `setup` folder.)
3. A black window shows what it is doing: checking Python, downloading Python 3.12, installing the backend, running its
   self-checks (automated tests), installing and building the web app.
4. Wait for **"Setup complete"**, then press any key to close the window.

If it stops with a red message, read it — it says what to install or fix (usually Python or Node.js), then run setup again.
Setup is safe to run as often as you like, and you run it again after downloading a newer version.

## Part 4 — Start the app

1. Double-click **`Start NiveshMitra.bat`**.
2. Two small minimised windows appear (the backend and the web app). **Keep them open** while you use the app.
3. Your browser opens **http://localhost:3000** after about 30 seconds. If it doesn't, open that address yourself.
4. To stop: double-click **`Stop NiveshMitra.bat`**, or close the two windows.

The app only works on this PC. Other devices on your Wi-Fi cannot reach it — that is deliberate.

## Part 5 — First sign-in (about 10 minutes, once)

The app uses **Sign in with Google** plus a code from an authenticator app. Google needs a free "login key" (a Client ID)
for your own copy of the app. The setup screen shows these steps too.

### Create your Google Client ID

1. Open https://console.cloud.google.com/ and sign in with your Google account.
2. At the top, click the project picker → **New project** → name it `NiveshMitra` → **Create** → make sure it is selected.
3. In the search bar type **Google Auth Platform** (older screens call it **OAuth consent screen**) → **Get started**.
   App name `NiveshMitra`, support email: yours, audience: **External**, contact email: yours → agree → **Create**.
4. Go to **Audience → Test users → Add users** → add your own Gmail address. (While the app is in "Testing", only the
   addresses listed here can ever sign in — exactly what we want.)
5. Go to **Clients** (or **Credentials**) → **Create client** → type **Web application** → name `NiveshMitra local`.
   Under **Authorized JavaScript origins** add both `http://localhost` and `http://localhost:3000`. Leave redirect URIs
   empty → **Create**.
6. Copy the **Client ID** (it ends with `.apps.googleusercontent.com`). You don't need the client secret.

### In the app

1. On the first-time setup screen paste the **Client ID** and your **Google email**, then **Save and continue**.
2. Click **Sign in with Google** and sign in on Google's own page. The app never sees your password.
3. Install **Google Authenticator** or **Microsoft Authenticator** on your phone, tap **+**, and scan the QR code shown.
   Type the 6-digit code. From now on every sign-in needs Google **plus** the code from your phone.
4. Answer the 10 short questions (your risk profile), read the SEBI reality check, and start the practice period.

## Part 6 — Connect your accounts (Settings)

Everything here is optional and entered by you. Keys are encrypted on this PC and only the last 4 characters are ever
shown again.

| Key | Where you get it | What it enables |
|---|---|---|
| **Groww API key (TOTP token)** and **TOTP secret** | groww.in → Trade API → API keys → **Generate TOTP token**. Market data needs Groww's **paid** Trade API plan | Stock prices, indices, tapes, sector pages, practice trading. Use **Settings → Test Groww connection** to see what your key can do |
| **Trendlyne MCP server URL** | trendlyne.com → your profile → Trendlyne MCP | News pulse |
| **Claude API key** | console.anthropic.com → API keys (create it inside a workspace, or also paste the workspace ID) | Friendlier explanations and news tone, within a monthly spending cap |
| **EODHD API key** | eodhd.com | Optional fundamentals vendor (later build step) |

The mutual-fund side needs **no keys at all**: fund data comes from AMFI and mfapi.in and downloads by itself the first
time (a few minutes for 1,000+ funds with 10 years of history).

## Part 7 — Day to day

- Start the app whenever you like; it fetches what it missed. The **Refresh** button at the top right pulls any finished
  session that isn't in yet.
- Each evening after the market closes, the dashboard updates the three-day row, the stock ideas and the practice plan.
- You act only through your broker's app. "Buy on Groww" buttons just open Groww's search page for that fund or stock.

## Updating to a newer version

1. Stop the app (`Stop NiveshMitra.bat`).
2. Download the new ZIP, extract it over the old folder **or** into a new folder and copy your old `data` folder into it.
3. Run `Setup NiveshMitra.bat` again. Your database is backed up automatically before any upgrade.

## Uninstalling

1. Stop the app and delete the folder. Everything the app created is inside it (`data` holds your database).
2. Optional: remove the encryption key — Windows **Credential Manager → Windows Credentials** → entry **NiveshMitra** → Remove.
3. Optional: delete the Google Cloud project you created.

## Troubleshooting

| Problem | Fix |
|---|---|
| Setup says Python or Node.js isn't installed | Install it from the link in Part 1 and run setup again. After installing Python, restart the setup window so it sees the new `py` command |
| Browser says "can't reach localhost:3000" | Run `Start NiveshMitra.bat` again and wait about 30 seconds |
| "Can't reach the Nivesh Mitra backend" | The backend window was closed. Run Stop, then Start |
| Google button says "origin not allowed" | In Google Cloud → your client → Authorized JavaScript origins, make sure both `http://localhost` and `http://localhost:3000` are listed |
| Google says "access blocked / not a test user" | Google Cloud → Google Auth Platform → Audience → Test users → add your Gmail |
| Authenticator code rejected | Check that your PC's clock is correct (Windows Settings → Time → Sync now) |
| Prices never appear | Settings → **Test Groww connection** shows exactly what your key can do. Live prices and history need Groww's paid plan |
| Lost your phone (authenticator) | Stop the app, rename `data\niveshmitra.db` to keep it safe, start again and go through sign-in afresh; or, if you are comfortable with SQLite, clear the `totp_secret_enc` value of your row in the `users` table and sign in again to set up a new authenticator |
