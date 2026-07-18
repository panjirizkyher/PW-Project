"""
DATA — SENTIMENT & MARKET PSYCHOLOGY (tanpa API key)
Sumber gratis:
  - CoinGecko /global  -> market_cap_change, btc_dominance, defi vol, sentiment(gecko)
  - CoinGecko /trending -> coins viral (proxy minat sosial)
  - alternative.me Fear&Greed (crypto sentiment)
Semua via requests (sudah ada). Offline-safe: kalau gagal, balik None / {}.
Tidak bergantung RSI/MA — ini LAPISAN data eksternal yg berbeda.
"""
from __future__ import annotations
import json
import urllib.request
import time
from datetime import datetime

_CACHE = {}
_CACHE_TTL = 60  # detik


def _get(url: str, timeout: int = 12):
    now = time.time()
    if url in _CACHE and (now - _CACHE[url][0]) < _CACHE_TTL:
        return _CACHE[url][1]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pewe-agent/1.0"})
        d = json.load(urllib.request.urlopen(req, timeout=timeout))
        _CACHE[url] = (now, d)
        return d
    except Exception:
        return None


def fear_greed(limit: int = 1) -> dict:
    """Fear&Greed index (0-100)."""
    d = _get("https://api.alternative.me/fng/?limit=%d" % limit)
    if not d or "data" not in d:
        return {}
    row = d["data"][0]
    return {"value": int(row.get("value", 0)),
            "classification": row.get("value_classification", "n/a"),
            "ts": row.get("timestamp")}


def coingecko_global() -> dict:
    """Ringkasan pasar global dari CoinGecko:
    btc_dominance, market_cap_change_24h, defi/stablecoin vol, 'sentiment' gecko.
    """
    d = _get("https://api.coingecko.com/api/v3/global")
    if not d or "data" not in d:
        return {}
    g = d["data"]
    out = {
        "total_mcap": g.get("total_market_cap", {}).get("usd"),
        "mcap_change_24h": g.get("market_cap_change_percentage_24h_usd"),
        "btc_dominance": g.get("market_cap_percentage", {}).get("btc"),
        "eth_dominance": g.get("market_cap_percentage", {}).get("eth"),
        "defi_vol": g.get("defi_volume_24h", {}).get("usd"),
        "stablecoin_vol": g.get("stablecoin_volume_24h", {}).get("usd"),
        "active_coins": g.get("active_cryptocurrencies"),
    }
    # gecko punya 'market_sentiment' di versi tertentu
    if "market_sentiment" in g:
        out["gecko_sentiment"] = g["market_sentiment"]
    return out


def coingecko_trending() -> list:
    """Top coin viral (proxy minat sosial)."""
    d = _get("https://api.coingecko.com/api/v3/search/trending")
    if not d or "coins" not in d:
        return []
    out = []
    for c in d["coins"][:7]:
        item = c.get("item", {})
        out.append({"symbol": item.get("symbol", "").upper(),
                    "name": item.get("name", ""),
                    "score": item.get("score"),
                    "rank": item.get("market_cap_rank")})
    return out


def market_psychology() -> dict:
    """Sintesis lapisan sentimen eksternal -> skor -100..+100.
    Bukan RSI/MA. Dipakai Vega/Chronos untuk modulate."""
    fg = fear_greed()
    g = coingecko_global()
    score = 0.0
    parts = []
    if fg:
        v = fg.get("value", 50)
        score += (v - 50) * 0.6          # F&G kontribusi
        parts.append(f"F&G {v} ({fg.get('classification')})")
    if g and g.get("mcap_change_24h") is not None:
        mc = g["mcap_change_24h"]
        score += max(-20, min(20, mc))    # perubahan mcap 24j
        parts.append(f"mcapΔ24h {mc:+.1f}%")
    if g and g.get("btc_dominance") is not None:
        dom = g["btc_dominance"]
        # dominasi tinggi = risk-off (flight to safety)
        if dom > 52:
            score -= 8
            parts.append(f"BTC.dom {dom:.1f}% (risk-off)")
        elif dom < 45:
            score += 6
            parts.append(f"BTC.dom {dom:.1f}% (alt-season)")
    score = max(-100.0, min(100.0, score))
    return {"score": round(score, 1),
            "label": "bullish" if score > 15 else ("bearish" if score < -15 else "neutral"),
            "parts": parts,
            "trending": coingecko_trending()}


if __name__ == "__main__":
    import pprint
    pprint.pprint(market_psychology())
