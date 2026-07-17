"""
AGENT 2 — RAFAEL (Technical Trader)
Price action + indikator deterministik. Hasilkan level S&R + struktur.
"""
from __future__ import annotations
import pandas as pd


class Rafael:
    def __init__(self):
        self.name = "RAFAEL"

    def analyze(self, df: pd.DataFrame) -> dict:
        if df.empty:
            return {"text": "(data kosong)", "bias": "n/a"}
        last = df.iloc[-1]
        ema50, ema200 = last.get("ema50"), last.get("ema200")
        r = last.get("rsi14")
        # struktur trend
        if pd.notna(ema50) and pd.notna(ema200):
            if ema50 > ema200:
                struct = "Uptrend (EMA50 > EMA200, HH/HL)"
                bias = "Bullish"
            elif ema50 < ema200:
                struct = "Downtrend (EMA50 < EMA200, LH/LL)"
                bias = "Bearish"
            else:
                struct = "Range / struktur netral"
                bias = "Netral"
        else:
            struct, bias = "EMA belum cukup data", "n/a"
        # S&R sederhana dari swing terakhir
        recent = df.tail(50)
        support = float(recent["low"].min())
        resistance = float(recent["high"].max())
        text = (
            f"Struktur: {struct}\n"
            f"RSI(14): {r:.1f} | EMA50: {ema50:.2f} | EMA200: {ema200:.2f}\n"
            f"S&R kunci — Support: {support:.2f} | Resistance: {resistance:.2f}"
        )
        return {"text": text, "bias": bias, "support": support, "resistance": resistance}
