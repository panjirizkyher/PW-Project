"""
MARKET DATA — via CCXT (public, tanpa API key untuk data).
Ambil OHLCV + ticker dari exchange manapun yang didukung ccxt.
"""
from __future__ import annotations
from typing import Optional
import ccxt
import pandas as pd


class MarketData:
    def __init__(self, exchange_id: str = "binance"):
        self.ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})

    def ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        try:
            raw = self.ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            return df
        except Exception as e:
            print(f"[MARKET] fetch gagal: {e}")
            return pd.DataFrame()

    def last_price(self, symbol: str) -> Optional[float]:
        try:
            t = self.ex.fetch_ticker(symbol)
            return float(t["last"])
        except Exception:
            return None
