"""
MARKET SNAPSHOT — simpan OHLCV token ter-scan ke logs/market.json (PEWE).
Dipakai dashboard untuk gambar chart real-time per token.
"""
from __future__ import annotations
import os, json
from core.indicators import add_indicators


def snapshot(market, symbols: list, timeframe: str = "1h", limit: int = 60) -> dict:
    """Ambil OHLCV tiap simbol, return dict {symbol: [[t,o,h,l,c], ...]}."""
    out = {}
    for sym in symbols:
        try:
            df = add_indicators(market.ohlcv(sym, timeframe, limit))
            if df is None or df.empty:
                continue
            rows = []
            for _, r in df.tail(limit).iterrows():
                rows.append([
                    int(r["ts"].timestamp()) if hasattr(r["ts"], "timestamp") else int(r["ts"]),
                    round(float(r["open"]), 4), round(float(r["high"]), 4),
                    round(float(r["low"]), 4), round(float(r["close"]), 4),
                ])
            last = float(df.iloc[-1]["close"])
            rsi = float(df.iloc[-1].get("rsi14", 0) or 0)
            out[sym] = {"ohlc": rows, "last": round(last, 4), "rsi": round(rsi, 2)}
        except Exception:
            continue
    os.makedirs("logs", exist_ok=True)
    with open("logs/market.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out
