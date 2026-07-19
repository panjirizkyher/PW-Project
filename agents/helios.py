"""
AGENT — SKAY (Trend Analyst)
Price action + indikator deterministik. Hasilkan level S&R + struktur + bias.
Versi upgrade: tambah ADX (kekuatan trend) + konfirmasi volume.
"""
from __future__ import annotations
import pandas as pd


class Helios:
    def __init__(self):
        self.name = "SKAY"

    def analyze(self, df: pd.DataFrame) -> dict:
        if df is None or df.empty:
            return {"text": "(data kosong)", "bias": "n/a"}
        last = df.iloc[-1]
        ema50, ema200 = last.get("ema50"), last.get("ema200")
        r = last.get("rsi14")
        adx = last.get("adx")
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
        adx_v = last.get("adx")
        adx_txt = f"{adx_v:.1f}" if pd.notna(adx_v) else "n/a"
        trend_strength = "n/a"
        if pd.notna(adx_v):
            trend_strength = "kuat" if adx_v >= 25 else ("lemah" if adx_v < 20 else "sedang")
        # S&R sederhana dari swing terakhir
        recent = df.tail(50)
        support = float(recent["low"].min())
        resistance = float(recent["high"].max())
        text = (
            f"Struktur: {struct}\n"
            f"RSI(14): {r:.1f} | EMA50: {ema50:.2f} | EMA200: {ema200:.2f}\n"
            f"ADX: {adx_txt} ({trend_strength})\n"
            f"S&R kunci — Support: {support:.2f} | Resistance: {resistance:.2f}"
        )
        return {"text": text, "bias": bias, "support": support, "resistance": resistance}
