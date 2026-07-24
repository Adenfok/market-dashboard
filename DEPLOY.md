# Deploy the dashboard as a free, shareable website

This publishes the dashboard to **GitHub Pages** (free, no server, no credit
card). A scheduled **GitHub Action** re-fetches the data every 6 hours and
republishes automatically, so the shared page stays current on its own.

You'll get a public URL like `https://YOURNAME.github.io/market-dashboard/`
that anyone can open — no login required for visitors.

---

## One-time setup (~10 minutes)

### 1. Get a GitHub account
Free at <https://github.com/signup> (skip if you already have one).

### 2. Create an empty repository
- Go to <https://github.com/new>
- **Repository name:** `market-dashboard` (or anything)
- Visibility: **Public** (required for free Pages)
- Do **not** add a README/.gitignore (this folder already has them)
- Click **Create repository**

### 3. Push this folder to it
Open a terminal in this project folder and run (replace `YOURNAME`/`market-dashboard`):

```bash
git init
git add .
git commit -m "Market timing dashboard"
git branch -M main
git remote add origin https://github.com/YOURNAME/market-dashboard.git
git push -u origin main
```

### 4. Let the Action write to the repo
Repo → **Settings** → **Actions** → **General** → *Workflow permissions* →
select **Read and write permissions** → **Save**.

### 5. Turn on GitHub Pages
Repo → **Settings** → **Pages** → *Build and deployment* →
Source: **Deploy from a branch** → Branch: **main**, folder: **/docs** → **Save**.

### 6. Do the first data refresh
Repo → **Actions** tab → click **Update market data** → **Run workflow**.
(After this, it runs itself every 6 hours.)

Wait ~1 minute, then open **`https://YOURNAME.github.io/market-dashboard/`**.
That's the link you share. 🎉

---

## How it works
- `generate.py` fetches the data, scores it, and writes `docs/data.json` plus
  `docs/index.html` (built from `dashboard.html`).
- `docs/` is what GitHub Pages serves — a plain static site, so it costs nothing
  and handles any number of visitors.
- `.github/workflows/update.yml` runs `generate.py` on a schedule and commits
  the refreshed `docs/data.json`. The page's **↻ Refresh** button just reloads
  that file, so visitors always see the latest published numbers.

## Updating the look
Edit `dashboard.html`, then either run `python generate.py` and commit, or just
push — the next scheduled run rebuilds `docs/index.html` from it.

## Notes
- Data refreshes on a schedule (every 6h), not live per-visitor — perfect for
  these indicators, which update daily/weekly.
- Change the cadence by editing the `cron` line in `.github/workflows/update.yml`.
- The page is clearly labelled **educational / not financial advice** — keep that
  disclaimer if you share it publicly.
- Heads-up: NAAIM announced it is moving to subscription-only access on
  2026-08-01; if that source stops responding, the app just shows the other four
  and the last saved NAAIM reading.
