"""
INDICATORS — helper deterministik (Rafael / Kodok).
RSI (Wilder), EMA, Fibonacci retracement.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    return 100 - (100 / (1 + rs))


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def fib_levels(low: float, high: float) -> dict:
    diff = high - low
    return {
        "0.0": low,
        "0.236": low + diff * 0.236,
        "0.382": low + diff * 0.382,
        "0.5": low + diff * 0.5,
        "0.618": low + diff * 0.618,
        "1.0": high,
    }


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi14"] = rsi(df["close"], 14)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    return df
