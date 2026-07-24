"""
backtest.py
-----------
Head-to-head backtest of v1 (current app scoring) vs v2 (backtest-informed
redesign) against forward S&P 500 returns. Both schemes live in scoring.py.

Data (see README 'Backtest data'):
    VIX, RSP RSI(14)  -> yfinance
    Fear & Greed      -> fng_history.csv    (2011+)
    AAII survey       -> aaii_history.csv    (1987+)
    NAAIM exposure    -> naaim_history.csv   (2006+)
Common window across all five = 2011 -> present (~15 years, multiple regimes).

Metrics per scheme:
    * Spearman rank corr of composite vs forward return (5/10/21/63/126/252d).
    * "Favorable" lift: forward return when composite is in the top zone,
      minus the unconditional baseline (top quintile = fair equal-n compare;
      also the app's favor>=70 band).
    * Composite terciles at 21d.
Run on the full 15yr AND the last 5yr (partial out-of-sample sanity check).
"""

from __future__ import annotations

import os
import warnings

import numpy as np
import pandas as pd

import scoring

warnings.filterwarnings("ignore")

HORIZONS = {"5d": 5, "10d": 10, "21d": 21, "63d": 63, "126d": 126, "252d": 252}
FULL_START = "2011-01-07"


def wilder_rsi(close, period=14):
    delta = close.diff()
    up = delta.clip(lower=0); down = -delta.clip(upper=0)
    ru = up.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rd = down.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return 100 - 100 / (1 + ru / rd)


def _need(path):
    if not os.path.exists(path):
        raise SystemExit(f"Missing {path}. Run the data-download step first.")
    return path


def build_panel():
    import yfinance as yf
    px = yf.download(["^GSPC", "^VIX", "RSP"], start="2009-06-01",
                     interval="1d", auto_adjust=True, progress=False)["Close"]
    spx = px["^GSPC"].dropna()
    vix = px["^VIX"].dropna()
    rsi = wilder_rsi(px["RSP"].dropna()).dropna()

    fng = pd.read_csv(_need("fng_history.csv"))
    fng = fng.rename(columns={fng.columns[0]: "date", fng.columns[1]: "val"})
    fng["date"] = pd.to_datetime(fng["date"])
    fng_s = pd.Series(fng.sort_values("date")["val"].values,
                      index=pd.to_datetime(fng.sort_values("date")["date"]))

    aaii = pd.read_csv(_need("aaii_history.csv"), parse_dates=["date"]).sort_values("date")
    aaii_s = pd.Series(aaii["spread"].values, index=aaii["date"])

    naaim = pd.read_csv(_need("naaim_history.csv"), parse_dates=["date"])
    naaim = naaim.drop_duplicates("date").sort_values("date")
    naaim_s = pd.Series(naaim["naaim"].values, index=naaim["date"])

    def asof(series, when):
        s = series[series.index <= when]
        return float(s.iloc[-1]) if len(s) else np.nan

    fridays = pd.date_range(start=FULL_START, end=spx.index.max(), freq="W-FRI")
    recs = []
    for wk in fridays:
        raw = {"vix": asof(vix, wk), "rsi": asof(rsi, wk), "fng": asof(fng_s, wk),
               "aaii": asof(aaii_s, wk), "naaim": asof(naaim_s, wk)}
        if any(np.isnan(v) for v in raw.values()):
            continue
        recs.append({"date": wk, **{f"raw_{k}": v for k, v in raw.items()},
                     "v1": scoring.composite_v1(raw),
                     "v2": scoring.composite_v2(raw)})
    panel = pd.DataFrame(recs).set_index("date")

    vals = spx.values
    def fwd(when, h):
        idx = spx.index.searchsorted(when, side="right") - 1
        if idx < 0 or idx + h >= len(vals):
            return np.nan
        return vals[idx + h] / vals[idx] - 1.0
    for name, h in HORIZONS.items():
        panel[f"fwd_{name}"] = [fwd(d, h) for d in panel.index]
    return panel


def spearman(a, b):
    m = a.notna() & b.notna()
    return float(a[m].rank().corr(b[m].rank())) if m.sum() >= 10 else np.nan


def lift(panel, score_col, ret_col, mask):
    d = panel[mask]
    r = d[ret_col].dropna(); base = panel[ret_col].mean()
    return r.mean() - base, (r > 0).mean(), len(r)


def report(panel, label):
    print("\n" + "#" * 72)
    print(f"# {label}: {panel.index.min().date()} -> {panel.index.max().date()} (n={len(panel)})")
    print("#" * 72)

    print("\nSpearman corr vs forward return  (higher = better timing signal):")
    print("  scheme   " + "".join(f"{h:>8}" for h in HORIZONS))
    for sc in ["v1", "v2"]:
        line = f"  {sc:<7}"
        for h in HORIZONS:
            line += f"{spearman(panel[sc], panel[f'fwd_{h}']):>8.2f}"
        print(line)

    for hz in ["21d", "63d"]:
        print(f"\nFavorable lift over baseline @ {hz}  "
              f"(baseline {panel[f'fwd_{hz}'].mean()*100:.2f}%):")
        for sc in ["v1", "v2"]:
            q80 = panel[sc].quantile(0.80)
            lq, wq, nq = lift(panel, sc, f"fwd_{hz}", panel[sc] >= q80)
            fav_mask = panel[sc] >= 70
            lf, wf, nf = lift(panel, sc, f"fwd_{hz}", fav_mask)
            fav_str = (f"{lf*100:+.2f}% (win {wf*100:.0f}%, n={nf})"
                       if nf >= 5 else f"n={nf} (too few)")
            print(f"  {sc}:  top-quintile {lq*100:+.2f}% (win {wq*100:.0f}%, n={nq})"
                  f"   |  favor>=70 {fav_str}")


def main():
    print("Loading prices + saved indicator histories...")
    panel = build_panel()
    panel.round(3).to_csv("backtest_panel.csv")
    report(panel, "FULL 15-YEAR (in-sample)")
    five = panel.index.max() - pd.Timedelta(days=365 * 5 + 3)
    report(panel[panel.index >= five], "LAST 5-YEAR (partial out-of-sample)")
    print("\nSaved -> backtest_panel.csv")
    print("\nCaveats: v2 shape/weights chosen on this same sample (in-sample, "
          "edge is an upper bound); overlapping windows autocorrelate.")


if __name__ == "__main__":
    main()
