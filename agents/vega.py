"""
AGENT — VEGA (Quant & Statistics)
Mantan Nakamoto X, di-upgrade jadi kuantitatif.
  - Fear&Greed sentimen crypto
  - On-chain placeholder (whale/flow) -> bisa diisi API
  - STATISTIK: hitung sederhana Sharpe/volatility + skew dari return window
    (deterministik, no LLM) sebagai input ke risk sizing.
"""
from __future__ import annotations
import numpy as np


class Vega:
    def __init__(self, llm=None):
        self.llm = llm
        self.name = "VEGA"

    def analyze(self, fg: dict, df=None) -> str:
        if not fg:
            return "(bukan aset crypto — lewati)"
        val = fg.get("value", "n/a")
        cls = fg.get("classification", "n/a")
        text = (
            f"Fear & Greed: {val} ({cls}). "
            + ("Greed tinggi — hati-hati top, jangan FOMO. " if isinstance(val, int) and val > 70
               else "Fear tinggi — akumulasi pelan, DYOR. " if isinstance(val, int) and val < 30
               else "Sentimen netral, tunggu konfirmasi. ")
        )
        # statistik sederhana dari return window
        if df is not None and not df.empty and "close" in df.columns:
            try:
                rets = df["close"].pct_change().dropna().tail(30).astype(float).values
                if len(rets) > 5:
                    mu = float(np.mean(rets))
                    sd = float(np.std(rets)) + 1e-9
                    sharpe = (mu / sd) * np.sqrt(365)
                    skew = float(np.mean(((rets - mu) / sd) ** 3))
                    text += (f"Stat 30-bar: vol~{sd*100:.2f}%, Sharpe~{sharpe:.2f}, "
                             f"skew~{skew:.2f}. " + ("Distribusi ekor-kiri — lindungi downside."
                                                    if skew < -0.5 else "Risk terukur."))
            except Exception:
                pass
        text += "HODL responsibly, wen moon tapi pake stop loss 😏"
        return text

    def stats(self, df) -> dict:
        """Return ringkasan statistik (dipakai sizing/risk)."""
        if df is None or df.empty or "close" not in df.columns:
            return {"sharpe": 0.0, "vol": 0.0, "skew": 0.0}
        try:
            rets = df["close"].pct_change().dropna().tail(30).astype(float).values
            mu = float(np.mean(rets)); sd = float(np.std(rets)) + 1e-9
            return {"sharpe": round(float((mu / sd) * np.sqrt(365)), 2),
                    "vol": round(float(sd), 4),
                    "skew": round(float(np.mean(((rets - mu) / sd) ** 3)), 2)}
        except Exception:
            return {"sharpe": 0.0, "vol": 0.0, "skew": 0.0}
