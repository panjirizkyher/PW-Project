"""
MARKET DATA — via CCXT (public, tanpa API key untuk data).
Ambil OHLCV + ticker dari exchange manapun yang didukung ccxt.
"""
from __future__ import annotations
from typing import Optional
import time
import ccxt
import pandas as pd


class MarketData:
    def __init__(self, exchange_id: str = "binance", testnet: bool = False):
        opts = {"enableRateLimit": True}
        self.ex = getattr(ccxt, exchange_id)(opts)
        if exchange_id == "binance" and testnet:
            # cara resmi ccxt: set_sandbox_mode arahkan host ke testnet.binance.vision
            self.ex.set_sandbox_mode(True)
        # cache OHLCV biar HFT tdk spam API (TTL 30s)
        self._ohlc_cache = {}
        self._ohlc_ttl = 30.0

    def ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200,
              use_cache: bool = True) -> pd.DataFrame:
        key = (symbol, timeframe, limit)
        if use_cache:
            c = self._ohlc_cache.get(key)
            if c and (c[1] + self._ohlc_ttl) > time.time():
                return c[0]
        try:
            raw = self.ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            if use_cache:
                self._ohlc_cache[key] = (df, time.time())
            return df
        except Exception as e:
            print(f"[MARKET] fetch gagal: {e}")
            # fallback ke cache lama kalau ada
            c = self._ohlc_cache.get(key)
            return c[0] if c else pd.DataFrame()

    def last_price(self, symbol: str) -> Optional[float]:
        try:
            t = self.ex.fetch_ticker(symbol)
            return float(t["last"])
        except Exception:
            return None
