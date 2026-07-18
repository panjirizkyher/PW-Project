"""
AGENT — VEGA (Quant & Statistics)
Mantan Nakamoto X, di-upgrade jadi kuantitatif + SENTIMEN EKSTERNAL.
  - Sentimen: Fear&Greed + market_psychology (dominasi, tren viral) — bukan cuma RSI
  - STATISTIK: Sharpe/volatility/skew dari return window
  - TRENDING: coin viral (proxy minat sosial) — data nyata dari CoinGecko
Semua deterministik (no LLM). Input ke risk sizing + filter entry Leviathan.
"""
from __future__ import annotations
import numpy as np


class Vega:
    def __init__(self, llm=None):
        self.llm = llm
        self.name = "VEGA"

    def analyze(self, fg: dict, df=None, psych: dict = None, trending: list = None) -> str:
        if not fg and not psych:
            return "(bukan aset crypto — lewati)"
        # sentimen berlapis
        parts = []
        if fg:
            val = fg.get("value", "n/a")
            cls = fg.get("classification", "n/a")
            parts.append(f"F&G {val} ({cls})")
        if psych:
            parts.append(f"Sentimen {psych.get('label')} (skor {psych.get('score')})")
        if trending:
            syms = ", ".join(t.get("symbol", "") for t in trending[:4])
            parts.append(f"Viral: {syms}")
        text = "Sentimen: " + "; ".join(parts) + ". "
        if fg and isinstance(fg.get("value"), int):
            v = fg["value"]
            text += ("Greed tinggi — hati-hati top, jangan FOMO. " if v > 70
                     else "Fear tinggi — akumulasi pelan, DYOR. " if v < 30
                     else "Sentimen netral, tunggu konfirmasi. ")
        # statistik return window
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

    def sentiment_ok(self, psych: dict = None, side: str = "buy") -> bool:
        """Filter: tolak entry long kalau sentimen bearish ekstrem (bukan RSI/MA)."""
        if not psych:
            return True
        if side == "buy" and psych.get("label") == "bearish" and psych.get("score", 0) < -20:
            return False
        return True
