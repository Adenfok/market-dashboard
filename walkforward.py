"""
walkforward.py
--------------
Out-of-sample (leak-free) test of data-driven weighting.

The v1-vs-v2 backtest was in-sample: v2's weights were chosen after seeing the
whole 2011-2026 sample. This script removes that advantage.

Procedure (expanding-window walk-forward, refit annually):
    * Use the v2 component favor MAPPINGS (economic shapes, not fitted).
    * At the start of each calendar year Y, fit component weights using ONLY
      data up to ~2 months before Y (so every training week's 21-day forward
      return is fully realised before the out-of-sample year begins -> no leak).
    * Weight = each component's Spearman corr with forward 21d return on the
      training window, clipped at 0 (a component that showed no/negative signal
      in-training gets zero weight), then normalised. Simple and robust; no
      unconstrained optimisation to overfit.
    * Apply those frozen weights to year Y (out-of-sample). Roll forward.

Then compare, on the pooled OUT-OF-SAMPLE weeks only:
    v1 equal-weight  |  v2 fixed hand-set weights  |  adaptive walk-forward
against forward 21d and 63d returns (Spearman + top-quintile lift).

If 'adaptive' >= 'v2 fixed' and both beat v1 out-of-sample, the reweighting
generalises. If adaptive collapses toward v1, the edge was in-sample noise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import scoring

TARGET = "fwd_21d"
COMPS = ["vix", "rsi", "fng", "aaii", "naaim"]


def spearman(a, b):
    m = a.notna() & b.notna()
    return float(a[m].rank().corr(b[m].rank())) if m.sum() >= 10 else np.nan


def main():
    p = pd.read_csv("backtest_panel.csv", parse_dates=["date"]).set_index("date")

    # component favor scores under the v2 mappings
    for c in COMPS:
        fn = getattr(scoring, f"v2_{c}")
        p[f"fv_{c}"] = p[f"raw_{c}"].apply(fn)
        fn1 = getattr(scoring, f"v1_{c}")
        p[f"f1_{c}"] = p[f"raw_{c}"].apply(fn1)

    years = range(2015, p.index.year.max() + 1)
    p["adaptive"] = np.nan
    p["v2fixed"] = p.apply(lambda r: scoring.weighted(
        {c: r[f"fv_{c}"] for c in COMPS}, scoring.V2_WEIGHTS), axis=1)
    p["v1equal"] = p.apply(lambda r: scoring.weighted(
        {c: r[f"f1_{c}"] for c in COMPS}, scoring.V1_WEIGHTS), axis=1)

    weight_log = []
    for Y in years:
        cutoff = pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=60)
        train = p[p.index <= cutoff]
        if len(train) < 150:
            continue
        w = {}
        for c in COMPS:
            rho = spearman(train[f"fv_{c}"], train[TARGET])
            w[c] = max(0.0, rho if not np.isnan(rho) else 0.0)
        if sum(w.values()) == 0:
            w = {c: 1.0 for c in COMPS}
        s = sum(w.values()); w = {c: w[c] / s for c in COMPS}
        weight_log.append({"year": Y, **{c: round(w[c], 3) for c in COMPS}})
        mask = p.index.year == Y
        p.loc[mask, "adaptive"] = p[mask].apply(
            lambda r: scoring.weighted({c: r[f"fv_{c}"] for c in COMPS}, w), axis=1)

    oos = p[p.index.year >= 2015].dropna(subset=["adaptive"])

    print("=" * 68)
    print(f"OUT-OF-SAMPLE weeks: {oos.index.min().date()} -> {oos.index.max().date()}"
          f"  (n={len(oos)})")
    print("=" * 68)
    print("\nSpearman corr vs forward return (out-of-sample only):")
    print(f"  {'scheme':<20}{'21d':>8}{'63d':>8}")
    for name, col in [("v1 equal-weight", "v1equal"),
                      ("v2 fixed weights", "v2fixed"),
                      ("adaptive walk-fwd", "adaptive")]:
        print(f"  {name:<20}{spearman(oos[col], oos['fwd_21d']):>8.2f}"
              f"{spearman(oos[col], oos['fwd_63d']):>8.2f}")

    print("\nTop-quintile favorable lift over baseline (out-of-sample):")
    for hz in ["21d", "63d"]:
        base = oos[f"fwd_{hz}"].mean()
        print(f"  @ {hz} (baseline {base*100:.2f}%):")
        for name, col in [("v1 equal-weight", "v1equal"),
                          ("v2 fixed weights", "v2fixed"),
                          ("adaptive walk-fwd", "adaptive")]:
            q = oos[col].quantile(0.80)
            r = oos[oos[col] >= q][f"fwd_{hz}"].dropna()
            print(f"    {name:<20}{ (r.mean()-base)*100:+.2f}%  (win {(r>0).mean()*100:.0f}%, n={len(r)})")

    wl = pd.DataFrame(weight_log).set_index("year")
    print("\nWeights the walk-forward LEARNED each year (leak-free):")
    print(wl.to_string())
    print("\nAverage learned weight:", {c: round(wl[c].mean(), 2) for c in COMPS})


if __name__ == "__main__":
    main()
