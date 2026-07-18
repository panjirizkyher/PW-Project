"""
AGENT — CHRONOS (Macro Timing Specialist)
Versi deterministik (tanpa LLM API key).
Analisa konteks makro/regim + TIMING dari data NYATA:
  - Fear&Greed (crypto sentiment)
  - Tren BTC (EMA50 vs EMA200) sebagai proxy risk-on/off
  - Volatilitas harian (ATR-ish)
  - Macro event (placeholder API)
  - TIMING: fase siklus dari posisi harga dlm range N-hari -> entry window
Return teks + regime + score (0..100) yg dipakai orchestrator modulate risk.
"""
from __future__ import annotations
from datetime import datetime


class Chronos:
    def __init__(self, llm=None):
        self.llm = llm
        self.name = "CHRONOS"

    def analyze(self, macro_events: list = None, fg: dict = None,
                btc_df=None, volatility: float = None) -> dict:
        fg_val = (fg or {}).get("value")
        fg_cls = (fg or {}).get("classification", "n/a")

        if fg_val is None:
            regime = "neutral"
            fg_part = "Fear&Greed: n/a (offline)"
        elif fg_val <= 25:
            regime = "risk_on"
            fg_part = f"Fear&Greed {fg_val} ({fg_cls}) — ekstrem fear, akumulasi selektif"
        elif fg_val <= 45:
            regime = "risk_on"
            fg_part = f"Fear&Greed {fg_val} ({fg_cls}) — fear, bias beli moderat"
        elif fg_val >= 75:
            regime = "risk_off"
            fg_part = f"Fear&Greed {fg_val} ({fg_cls}) — greed ekstrem, waspada eksposur"
        else:
            regime = "neutral"
            fg_part = f"Fear&Greed {fg_val} ({fg_cls}) — netral"

        trend_part = "Tren BTC: n/a"
        btc_bias = "neutral"
        timing = "window: netral"
        if btc_df is not None and not btc_df.empty and "ema50" in btc_df.columns:
            try:
                e50 = float(btc_df.iloc[-1]["ema50"])
                e200 = float(btc_df.iloc[-1]["ema200"])
                if e50 > e200 * 1.01:
                    btc_bias = "up"
                    trend_part = f"BTC uptrend (EMA50 {e50:,.0f} > EMA200 {e200:,.0f}) — risk-on"
                elif e50 < e200 * 0.99:
                    btc_bias = "down"
                    trend_part = f"BTC downtrend (EMA50 {e50:,.0f} < EMA200 {e200:,.0f}) — risk-off"
                else:
                    trend_part = f"BTC rangka (EMA50≈EMA200) — netral"
                # TIMING: posisi harga dalam 20-day range -> beli saat di bawah tengah
                lo = float(btc_df["low"].tail(20).min())
                hi = float(btc_df["high"].tail(20).max())
                last = float(btc_df.iloc[-1]["close"])
                if hi > lo:
                    pos = (last - lo) / (hi - lo)
                    if pos < 0.4:
                        timing = "window: AKUMULASI (harga di bawah 40% range 20h)"
                    elif pos > 0.7:
                        timing = "window: DISTRIBUSI (harga di atas 70% range 20h)"
                    else:
                        timing = "window: netral"
            except Exception:
                pass

        vol_part = "Volatilitas: n/a"
        if volatility is not None:
            vol_part = (f"Volatilitas harian ~{volatility*100:.1f}% — "
                       + ("tinggi, perketat SL" if volatility > 0.06
                          else "wajar, kondusif untuk entri"))

        ev = macro_events or [{"event": "FOMC/NFP/CPI (isi via API makro)", "impact": "high"}]
        ev_part = "Katalis: " + "; ".join(f"{e.get('event','?')} [{e.get('impact','?')}]" for e in ev[:3])

        score = 50.0
        if regime == "risk_on":
            score += 20
        elif regime == "risk_off":
            score -= 20
        if btc_bias == "up":
            score += 15
        elif btc_bias == "down":
            score -= 15
        if volatility is not None and volatility > 0.06:
            score -= 5
        score = max(0.0, min(100.0, score))

        text = (f"{fg_part}.\n{trend_part}.\n{vol_part}.\n{timing}.\n{ev_part}.\n"
                f"Regim: {regime.upper()} (skor {score:.0f}/100).")

        return {"text": text, "regime": regime, "score": round(score, 1)}
