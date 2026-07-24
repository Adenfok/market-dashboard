"""
market_data.py
--------------
Fetches five market/sentiment indicators and turns them into a single
"contrarian composite" entry-timing score for the US equity market.

Indicators
    1. VIX .................. CBOE Volatility Index          (Yahoo Finance ^VIX)
    2. RSP RSI(14) .......... 14-day RSI of the S&P 500      (Yahoo Finance RSP)
                             Equal-Weight ETF (RSP)
    3. Fear & Greed Index ... CNN Fear & Greed Index         (CNN dataviz API)
    4. AAII Survey .......... Retail bull/bear sentiment      (aaii.com sentiment.xls)
    5. NAAIM Exposure ....... Active manager equity exposure  (naaim.org)

Scoring philosophy (CONTRARIAN):
    Every indicator is mapped to a 0-100 "entry favorability" sub-score where
    HIGHER  = more fear / oversold / defensive positioning  -> better time to BUY
    LOWER   = more greed / overbought / aggressive crowding  -> worse time to buy
    The composite is the equal-weighted average of the available sub-scores.

    This is a SENTIMENT / MEAN-REVERSION framework. It is educational and is
    NOT financial advice.
"""

from __future__ import annotations

import io
import re
import time
import warnings
from datetime import datetime, timezone

import pandas as pd
import requests

import scoring  # v2 favor mappings, weights, and verdict bands

warnings.filterwarnings("ignore")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA}
TIMEOUT = 25

# ----------------------------------------------------------------------------
# Simple in-process cache so repeated dashboard refreshes don't hammer sources.
# ----------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 300  # seconds


def _cached(key: str, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def clear_cache() -> None:
    _CACHE.clear()


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ----------------------------------------------------------------------------
# Persistent "last good" store: if a source is transiently throttled/down we
# fall back to the most recent successful reading (flagged as stale) so the
# dashboard stays useful instead of dropping the indicator entirely.
# ----------------------------------------------------------------------------
import json as _json
import os as _os

_STORE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "lastgood.json")


def _load_store() -> dict:
    try:
        with open(_STORE, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save_store(store: dict) -> None:
    try:
        with open(_STORE, "w", encoding="utf-8") as f:
            _json.dump(store, f)
    except Exception:  # noqa: BLE001
        pass


# ============================================================================
# 1 & 2.  Yahoo Finance: VIX level and RSP RSI(14)
# ============================================================================
def _wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    roll_down = down.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = roll_up / roll_down
    return 100 - 100 / (1 + rs)


def _yahoo():
    import yfinance as yf
    data = yf.download(["^VIX", "RSP"], period="6mo",
                       interval="1d", progress=False, auto_adjust=True)
    close = data["Close"]

    vix_series = close["^VIX"].dropna()
    vix = float(vix_series.iloc[-1])
    vix_date = vix_series.index[-1].strftime("%Y-%m-%d")

    rsp_close = close["RSP"].dropna()
    rsp_price = float(rsp_close.iloc[-1])
    rsi_series = _wilder_rsi(rsp_close).dropna()
    rsi = float(rsi_series.iloc[-1])
    rsp_date = rsp_close.index[-1].strftime("%Y-%m-%d")
    return {"vix": vix, "vix_date": vix_date,
            "rsi": rsi, "rsp_price": rsp_price, "rsp_date": rsp_date}


def get_vix():
    try:
        y = _cached("yahoo", _yahoo)
        vix = y["vix"]
        # v2 mapping (VIX 12 -> 0 complacency, 40 -> 100 panic; the best component).
        favor = scoring.v2_vix(vix)
        return {"ok": True, "value": round(vix, 2), "asof": y["vix_date"],
                "favor": round(favor, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}


def get_rsp_rsi():
    try:
        y = _cached("yahoo", _yahoo)
        rsi = y["rsi"]
        # v2 mapping (RSI 70 -> 0 overbought, 30 -> 100 oversold).
        favor = scoring.v2_rsi(rsi)
        return {"ok": True, "value": round(rsi, 1), "price": round(y["rsp_price"], 2),
                "asof": y["rsp_date"], "favor": round(favor, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}


# ============================================================================
# 3.  CNN Fear & Greed Index
# ============================================================================
def _cnn():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/current"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_fear_greed():
    try:
        j = _cached("cnn", _cnn)
        score = float(j["score"])
        rating = str(j.get("rating", "")).title()
        ts = j.get("timestamp", "")
        try:
            asof = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            asof = ""
        # v2 non-linear mapping: reward extreme fear, greed ~neutral, mild
        # euphoria penalty (the linear 100-score flip was invalid).
        favor = scoring.v2_fng(score)
        return {"ok": True, "value": round(score, 1), "rating": rating,
                "asof": asof, "favor": round(favor, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}


# ============================================================================
# 4.  AAII Investor Sentiment Survey
# ============================================================================
def _aaii():
    url = "https://www.aaii.com/files/surveys/sentiment.xls"
    # A Referer is required or aaii.com serves an HTML throttle page instead of the file.
    hdrs = dict(HEADERS, **{
        "Referer": "https://www.aaii.com/sentimentsurvey",
        "Accept": "application/vnd.ms-excel,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    r = requests.get(url, headers=hdrs, timeout=TIMEOUT)
    r.raise_for_status()
    if not r.content[:4] == b"\xd0\xcf\x11\xe0":  # OLE2 (.xls) magic number
        raise ValueError("aaii.com returned a non-Excel response (throttled?)")
    df = pd.read_excel(io.BytesIO(r.content), sheet_name="SENTIMENT",
                       header=None, engine="xlrd")
    # Column layout (0-indexed):
    #   0 Date | 1 Bullish | 2 Neutral | 3 Bearish | 7 Bull-Bear Spread
    rows = []
    for _, row in df.iterrows():
        d = row[0]
        if isinstance(d, datetime) or isinstance(d, pd.Timestamp):
            try:
                bull = float(row[1]); neut = float(row[2]); bear = float(row[3])
            except (TypeError, ValueError):
                continue
            if pd.isna(bull) or pd.isna(bear):
                continue
            rows.append((pd.Timestamp(d), bull, neut, bear))
    rows.sort(key=lambda x: x[0])
    return rows[-1]


def get_aaii():
    try:
        d, bull, neut, bear = _cached("aaii", _aaii)
        # values are stored as fractions (0.38 == 38%)
        bull *= 100; neut *= 100; bear *= 100
        spread = bull - bear
        # v2 one-sided mapping: bearish crowd rewarded; bullish crowd is noise.
        favor = scoring.v2_aaii(spread)
        return {"ok": True, "bullish": round(bull, 1), "neutral": round(neut, 1),
                "bearish": round(bear, 1), "spread": round(spread, 1),
                "asof": d.strftime("%Y-%m-%d"), "favor": round(favor, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}


# ============================================================================
# 5.  NAAIM Exposure Index
# ============================================================================
def _naaim():
    url = "https://naaim.org/programs/naaim-exposure-index/"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    t = r.text
    a = t.find("function drawNaaimChart")
    b = t.find("function drawSpChart")
    seg = t[a: b if b > a else a + 200000]
    pts = re.findall(r"new Date\((\d+),\s*(\d+),\s*(\d+)\)\s*,\s*(-?\d+\.?\d*)", seg)
    if not pts:
        raise ValueError("no NAAIM data points parsed")
    y, m, dd, val = pts[-1]
    # JS Date months are 0-indexed.
    asof = datetime(int(y), int(m) + 1, int(dd)).strftime("%Y-%m-%d")
    return float(val), asof


def get_naaim():
    try:
        val, asof = _cached("naaim", _naaim)
        # v2 mapping (linear): low exposure (defensive) -> favorable.
        favor = scoring.v2_naaim(val)
        return {"ok": True, "value": round(val, 1), "asof": asof,
                "favor": round(favor, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}


# ============================================================================
# Composite + verdict  (v2: weighted, with recalibrated bands -- see scoring.py)
# ============================================================================
# Map dashboard indicator keys -> scoring.py component keys.
_SCORE_KEY = {"vix": "vix", "rsp_rsi": "rsi", "fear_greed": "fng",
              "aaii": "aaii", "naaim": "naaim"}


def build_report() -> dict:
    indicators = {
        "vix": get_vix(),
        "rsp_rsi": get_rsp_rsi(),
        "fear_greed": get_fear_greed(),
        "aaii": get_aaii(),
        "naaim": get_naaim(),
    }

    # Fall back to last-good readings for any source that failed this run.
    store = _load_store()
    changed = False
    for key, res in indicators.items():
        if res.get("ok"):
            store[key] = res
            changed = True
        else:
            prev = store.get(key)
            if prev and prev.get("ok"):
                fallback = dict(prev)
                fallback["stale"] = True
                fallback["fetch_error"] = res.get("error", "")
                indicators[key] = fallback
    if changed:
        _save_store(store)

    favs = {_SCORE_KEY[k]: v["favor"] for k, v in indicators.items() if v.get("ok")}
    if favs:
        composite = round(scoring.weighted(favs, scoring.V2_WEIGHTS), 1)
        headline, tone, detail = scoring.verdict_v2(composite)
    else:
        composite = None
        headline, tone, detail = scoring.verdict_v2(None)

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "indicators": indicators,
        "composite": composite,
        "available": len(favs),
        "verdict": {"headline": headline, "tone": tone, "detail": detail},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(build_report(), indent=2))
