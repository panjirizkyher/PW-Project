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
            df = self._fetch_ohlcv_paginated(symbol, timeframe, limit)
            if use_cache:
                self._ohlc_cache[key] = (df, time.time())
            return df
        except Exception as e:
            print(f"[MARKET] fetch gagal: {e}")
            # fallback ke cache lama kalau ada
            c = self._ohlc_cache.get(key)
            return c[0] if c else pd.DataFrame()

    def _fetch_ohlcv_paginated(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Ambil hingga `limit` candle via paginasi (ccxt max 1000/call).
        Pakai `since` mundur dari sekarang supaya dapat window historis panjang
        (mis. 4320 candle 1h = ~6 bulan)."""
        MAX = 1000
        tf_ms = self._tf_to_ms(timeframe)
        frames = []
        remaining = limit
        end_ts = int(time.time() * 1000)
        while remaining > 0:
            chunk = min(MAX, remaining)
            raw = self.ex.fetch_ohlcv(symbol, timeframe, limit=chunk, since=end_ts - chunk * tf_ms)
            if not raw:
                break
            df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
            frames.append(df)
            # lanjut mundur ke candle sebelum yg paling awal
            first_ts = int(df["ts"].iloc[0])
            end_ts = first_ts
            remaining -= len(raw)
            if len(raw) < chunk:
                break
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        return out

    @staticmethod
    def _tf_to_ms(timeframe: str) -> int:
        units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
        n = int(timeframe[:-1]); u = timeframe[-1]
        return n * units.get(u, 3_600_000)

    def last_price(self, symbol: str) -> Optional[float]:
        try:
            t = self.ex.fetch_ticker(symbol)
            return float(t["last"])
        except Exception:
            return None
