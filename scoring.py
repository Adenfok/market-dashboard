"""
scoring.py
----------
Two scoring schemes for the contrarian entry-timing composite, so the app and
the backtest share one source of truth.

v1  = the original hand-designed scheme (equal weights, linear contrarian flip
      on every indicator). This is what market_data.py currently ships.

v2  = the backtest-informed redesign:
   * Weights by demonstrated 15yr forward-return lift, not equal:
        VIX .30  AAII .22  RSI .20  NAAIM .16  Fear&Greed .12
   * Fear & Greed: NON-LINEAR. Reward only the extreme-fear tail; treat greed
     as roughly neutral (greed = uptrend, historically ~baseline returns);
     only mild penalty for extreme greed (euphoria). Fixes the invalid
     100-minus-score linear flip that penalised healthy bull-market greed.
   * AAII: ONE-SIDED. Its bearish extreme predicts rebounds; its bullish
     extreme carries ~no signal, so don't drag the score down for it.
   * NAAIM: NON-LINEAR. Only informative at defensive extremes (low exposure);
     flat/neutral through the normal 50-100 range.
   * VIX & RSI: unchanged (VIX is the best, two-sided signal; RSI is steady).

NOTE ON HONESTY: v2's shape and weights were chosen from the same 2011-2026
sample used to test them, so the head-to-head is IN-SAMPLE and v2's edge is an
upper bound. The mappings are coarse/round (economic reasoning, not numeric
optimisation) to limit overfitting, and backtest.py also reports the last-5yr
slice as a partial out-of-sample sanity check.
"""

from __future__ import annotations
import numpy as np


def clamp(x, lo=0.0, hi=100.0):
    return float(np.clip(x, lo, hi))


# ============================ v1 (current app) =============================
def v1_vix(v):    return clamp((v - 12.0) / 28.0 * 100.0)
def v1_rsi(r):    return clamp((70.0 - r) / 40.0 * 100.0)
def v1_fng(s):    return clamp(100.0 - s)
def v1_aaii(sp):  return clamp(50.0 - sp * (50.0 / 40.0))
def v1_naaim(n):  return clamp(100.0 - n)

V1_WEIGHTS = {"vix": .20, "rsi": .20, "fng": .20, "aaii": .20, "naaim": .20}


# ============================ v2 (improved) ================================
def v2_vix(v):    return clamp((v - 12.0) / 28.0 * 100.0)     # unchanged anchor
def v2_rsi(r):    return clamp((70.0 - r) / 40.0 * 100.0)     # unchanged


def v2_fng(s):
    """Non-linear: reward extreme fear, keep greed ~neutral, mild euphoria penalty."""
    if s <= 10:  return 100.0
    if s <= 25:  return 100.0 - (s - 10) / 15 * 25      # 100 -> 75
    if s <= 50:  return 75.0 - (s - 25) / 25 * 15       # 75 -> 60
    if s <= 80:  return 60.0 - (s - 50) / 30 * 10       # 60 -> 50 (greed neutral)
    return max(35.0, 50.0 - (s - 80) / 20 * 15)         # 50 -> 35 (euphoria)


def v2_aaii(sp):
    """One-sided: bearish crowd rewarded; bullish crowd only mildly discounted."""
    if sp <= 0:  return clamp(55.0 + (-sp) * (45.0 / 20.0))   # sp 0->55, -20->100
    return clamp(55.0 - sp * 0.375)                           # sp +40->40 (mild)


def v2_naaim(n):
    """Linear. The best/worst-100 analysis showed raw NAAIM separates strongly
    (managers ~54 before the best weeks vs ~67 before the worst); an earlier
    non-linear mapping flattened the 40-100 range and threw that signal away."""
    return clamp(100.0 - n)


# Weights set to the walk-forward LEARNED average (leak-free, see walkforward.py),
# not hand-picked: VIX is the stable anchor; AAII lower and remapped-F&G higher
# than the first hand-set guess.
V2_WEIGHTS = {"vix": .31, "rsi": .21, "naaim": .17, "fng": .16, "aaii": .15}


# ============================ composites ===================================
def favors_v1(raw: dict) -> dict:
    fns = {"vix": v1_vix, "rsi": v1_rsi, "fng": v1_fng, "aaii": v1_aaii, "naaim": v1_naaim}
    return {k: fns[k](raw[k]) for k in fns if k in raw and raw[k] is not None}


def favors_v2(raw: dict) -> dict:
    fns = {"vix": v2_vix, "rsi": v2_rsi, "fng": v2_fng, "aaii": v2_aaii, "naaim": v2_naaim}
    return {k: fns[k](raw[k]) for k in fns if k in raw and raw[k] is not None}


def weighted(favs: dict, weights: dict) -> float:
    tot = sum(weights[k] for k in favs)
    if tot == 0:
        return float("nan")
    return sum(favs[k] * weights[k] for k in favs) / tot


def composite_v1(raw): return weighted(favors_v1(raw), V1_WEIGHTS)
def composite_v2(raw): return weighted(favors_v2(raw), V2_WEIGHTS)


# ============================ v2 verdict bands =============================
# Thresholds recalibrated from the 15yr threshold sweep: the forward-return
# edge (win rate stepping above baseline) begins around composite 60, and the
# rare >=70 band is the strongest. 57-59 was no better than neutral, so it was
# folded down. Numbers quoted are 15yr, 21-day forward S&P (baseline ~+1.1%/67%).
def verdict_v2(score):
    """Return (headline, tone_key, detail)."""
    if score is None:
        return ("No data available", "neutral",
                "All data sources failed to load. Check your connection and retry.")
    if score >= 70:
        return ("Strong buy — deep-fear extreme", "strong-buy",
                "Top band (~6% of weeks, deep fear). Historically the strongest setups: "
                "about +4.6% over the next month (74% positive) and ~+9.7% over 3 months.")
    if score >= 60:
        return ("Buy — favorable entry", "buy",
                "Above ~60, where the historical edge begins: about +3.7% over the next "
                "month with a ~76% positive rate, vs a ~1% buy-anytime baseline.")
    if score >= 43:
        return ("Neutral — no timing edge", "neutral",
                "Forward returns here are close to simply staying invested; sentiment "
                "offers no reliable contrarian edge right now.")
    if score >= 30:
        return ("Caution — optimism building", "caution",
                "Leaning greedy / complacent. Not a strong sell, but a below-average "
                "spot to add new exposure.")
    return ("Poor — greed / complacency", "poor",
            "Widespread greed and aggressive positioning. Historically a below-average "
            "time to initiate new longs.")
