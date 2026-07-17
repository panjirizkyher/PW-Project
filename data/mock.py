"""
MOCK DATA — synthetic OHLCV supaya pipeline bisa ditest tanpa network.
Validasi: indicators, sinyal, risk gate, paper fill, briefing render semua jalan.
JANGAN pakai untuk trading nyata.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def mock_ohlcv(n: int = 200, start_price: float = 60000.0, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # random walk dengan drift agar ada trend + siklus RSI
    drift = 0.0002
    rets = rng.normal(drift, 0.01, n)
    closes = start_price * np.exp(np.cumsum(rets))
    highs = closes * (1 + np.abs(rng.normal(0, 0.004, n)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.004, n)))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    vol = rng.uniform(100, 1000, n)
    ts = [datetime.now() - timedelta(hours=n - i) for i in range(n)]
    df = pd.DataFrame({
        "ts": ts, "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vol,
    })
    return df
