"""
AGENT 1 — PROF. MARCUS (Chief Macro Analyst)
Versi deterministik (tanpa LLM API key).
Analisa konteks makro/regim pasar dari data NYATA:
  - Fear&Greed (crypto sentiment)
  - Tren BTC (EMA50 vs EMA200) sebagai proxy risk-on/off
  - Volatilitas harian (ATR-ish)
  - Event makro placeholder (bisa diisi API nanti)
Return teks analisis + skor regim (risk_on/risk_off/neutral) yg dipakai
orchestrator untuk modulate risk (bukan cuma hiasan).
"""
from __future__ import annotations
from datetime import datetime


class Marcus:
    def __init__(self, llm=None):
        self.llm = llm
        self.name = "PROF. MARCUS"

    def analyze(self, macro_events: list = None, fg: dict = None,
                btc_df=None, volatility: float = None) -> dict:
        """
        Return dict:
          text  : analisa (Indonesian)
          regime: 'risk_on' | 'risk_off' | 'neutral'
          score : 0..100 (semakin tinggi = semakin risk-on)
        """
        fg_val = (fg or {}).get("value")
        fg_cls = (fg or {}).get("classification", "n/a")

        # --- regime dari F&G ---
        if fg_val is None:
            regime = "neutral"
            fg_part = "Fear&Greed: n/a (offline)"
        elif fg_val <= 25:
            regime = "risk_on"          # extreme fear = peluang beli (counter-trend)
            fg_part = f"Fear&Greed {fg_val} ({fg_cls}) — ekstrem fear, akumulasi selektif"
        elif fg_val <= 45:
            regime = "risk_on"
            fg_part = f"Fear&Greed {fg_val} ({fg_cls}) — fear, bias beli moderat"
        elif fg_val >= 75:
            regime = "risk_off"         # extreme greed = waspada
            fg_part = f"Fear&Greed {fg_val} ({fg_cls}) — greed ekstrem, waspada eksposur"
        else:
            regime = "neutral"
            fg_part = f"Fear&Greed {fg_val} ({fg_cls}) — netral"

        # --- tren BTC (proxy makro) ---
        trend_part = "Tren BTC: n/a"
        btc_bias = "neutral"
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
            except Exception:
                pass

        # --- volatilitas ---
        vol_part = "Volatilitas: n/a"
        if volatility is not None:
            vol_part = (f"Volatilitas harian ~{volatility*100:.1f}% — "
                       + ("tinggi, perketat SL" if volatility > 0.06
                          else "wajar, kondusif untuk entri"))

        # --- event placeholder ---
        ev = macro_events or [{"event": "FOMC/NFP/CPI (isi via API makro)", "impact": "high"}]
        ev_part = "Katalis: " + "; ".join(f"{e.get('event','?')} [{e.get('impact','?')}]" for e in ev[:3])

        # --- skor regime (0..100) ---
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

        text = (f"{fg_part}.\n{trend_part}.\n{vol_part}.\n{ev_part}.\n"
                f"Regim: {regime.upper()} (skor {score:.0f}/100).")

        return {"text": text, "regime": regime, "score": round(score, 1)}
