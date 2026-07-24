# US Equity Market — Entry Timing Dashboard

A small local web app that pulls five widely-watched market and sentiment
indicators, scores each one on a **contrarian** 0–100 scale, and combines them
into a single verdict on whether now looks like a good time to add exposure to
the US equity market.

| Indicator | What it measures | Source |
|-----------|------------------|--------|
| **VIX** | Expected volatility / fear | Yahoo Finance (`^VIX`) |
| **RSP RSI(14)** | Overbought/oversold momentum of the S&P 500 **equal-weight** ETF | Yahoo Finance (`RSP`) |
| **Fear & Greed Index** | CNN's composite market mood | CNN dataviz API |
| **AAII Survey** | Retail investor bull/bear sentiment | aaii.com weekly survey |
| **NAAIM Exposure** | How long/short active managers actually are | naaim.org |

## Scoring logic (contrarian)

Each indicator becomes an *entry-favorability* sub-score from 0 to 100:

- **Higher = more fear / oversold / defensive positioning → historically a better time to buy.**
- **Lower = more greed / overbought / crowded positioning → historically a worse time to buy.**

The app ships the **v2** scheme (`scoring.py`), whose weights and mappings were
tuned on 15 years (2011–26) and validated out-of-sample (`backtest.py`,
`walkforward.py`). Each indicator's favor score (0–100), and its weight:

| Indicator | Weight | Formula | Notes |
|-----------|:------:|---------|-------|
| VIX | **0.31** | `(VIX - 12) / 28 * 100` | best component (both tails carry signal) |
| RSP RSI(14) | 0.21 | `(70 - RSI) / 40 * 100` | 70 → 0 overbought, 30 → 100 oversold (Wilder) |
| NAAIM | 0.17 | `100 - exposure` | defensive → high, fully long → low |
| Fear & Greed | 0.16 | non-linear | reward extreme fear; **greed ≈ neutral**; mild euphoria penalty |
| AAII survey | 0.15 | one-sided | bearish crowd → up to 100; **bullish ignored** |
| **Composite** | — | `weighted average` | renormalized over whichever loaded, 0–100 |

Verdict bands were recalibrated from a threshold sweep — the historical edge
begins around **60**, so the old "lean buy 57–69" was retired:

| Composite | Verdict | 15yr forward (21d) |
|-----------|---------|--------------------|
| ≥ 70 | **Strong buy** | ~+4.6% (74% positive) |
| 60–69 | **Buy** | ~+3.7% (76% positive) |
| 43–59 | Neutral — no edge | ≈ baseline (+1.1%) |
| 30–42 | Caution | below-average |
| < 30 | Poor | below-average |

The original equal-weighted linear scheme is kept as **v1** in `scoring.py` for
reference. Run `python backtest.py` to reproduce the v1-vs-v2 comparison.

## Run it

Double-click **`run.bat`**, or from a terminal:

```
pip install -r requirements.txt
python app.py
```

A browser tab opens at <http://127.0.0.1:8765>. Click **↻ Refresh data** to pull
fresh numbers (data is cached for 5 minutes to be polite to the sources).

You can also print a plain-text report without the web UI:

```
python market_data.py
```

## Share it online (free)

Publish it as a public website on **GitHub Pages** — no server, no cost, and a
scheduled GitHub Action keeps the data fresh automatically. Full steps in
**[DEPLOY.md](DEPLOY.md)**. In short: push this folder to a public GitHub repo,
enable Pages on the `/docs` folder, and share the resulting
`https://YOURNAME.github.io/...` link.

To build the static site locally first: `python generate.py` → open `docs/index.html`.

## Files

- `app.py` — local web server (Python standard library only)
- `market_data.py` — data fetching + scoring engine
- `scoring.py` — v1 / v2 favor mappings, weights, verdict bands
- `dashboard.html` — the UI (single source for both local and web)
- `generate.py` — builds the static site into `docs/` for hosting
- `backtest.py` / `walkforward.py` — validation
- `.github/workflows/update.yml` — scheduled data refresh for the website
- `requirements.txt` / `run.bat` — setup & launcher

## Disclaimer

For educational purposes only. This is **not financial advice** and not a
recommendation to buy or sell any security. Sentiment indicators are noisy and
past patterns do not guarantee future results. Do your own research.
