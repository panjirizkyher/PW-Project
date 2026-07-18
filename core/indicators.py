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

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder) — ukur volatilitas buat SL/TP realistis."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift()
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()

def bollinger(close: pd.Series, period: int = 20, n_std: float = 2.0):
    """Kembalikan (mid, upper, lower) sebagai pd.Series."""
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    upper = mid + n_std * sd
    lower = mid - n_std * sd
    return mid, upper, lower


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # guard: df kosong / tanpa kolom 'close' (fetch OHLCV gagal) -> jangan KeyError
    if df.empty or "close" not in df.columns:
        for c in ("rsi14", "ema50", "ema200", "adx", "atr14", "bb_upper", "bb_lower", "bb_mid"):
            df[c] = pd.Series(dtype="float64")
        return df
    df["rsi14"] = rsi(df["close"], 14)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["adx"] = adx(df, 14)  # kekuatan trend (Helios)
    df["atr14"] = atr(df, 14)  # volatilitas (Leviathan SL/TP)
    mid, up, lo = bollinger(df["close"], 20, 2.0)
    df["bb_mid"], df["bb_upper"], df["bb_lower"] = mid, up, lo
    return df


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX sederhana (Wilder) — ukur kekuatan trend, bukan arah."""
    high, low, close = df["high"], df["low"], df["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = np.maximum.reduce([
        (high - low).abs().values,
        (high - close.shift()).abs().values,
        (low - close.shift()).abs().values,
    ])
    atr = pd.Series(tr, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-12)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-12)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-12)
    return dx.ewm(alpha=1/period, adjust=False).mean()
