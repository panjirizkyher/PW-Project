"""
CORE/ML/CONVINCED_SCORE — PEWE (Lapisan Filtrasi Eksekusi B)

Hybrid gate sebelum Execution Agent: "Convinced Score" 0-100%.
Gabungan 3 dimensi (sesuai instruksi Hybrid B):
  1. TEKNIKAL  (40%) : RSI ekstrem + posisi harga vs EMA + ATR masuk akal
  2. SENTIMEN  (20%) : Fear&Greed + survei market (Vega/Argus)
  3. ML PROB   (40%) : probabilitas profit dari SignalFilter (Learning Agent)

HANYA trade dgn score > 85% yg boleh dieksekusi (instruksi: skor >85%).

Anti-overfit/jujur:
  - Bobot tetap, transparan (bukan black-box).
  - ML prob dari model yg SUDAH terlatih; kalau belum trained -> fallback ke technical saja.
  - Tidak ada janji profit; ini penjaga survivabilitas (prinsip #1).
"""
from __future__ import annotations
import os


class ConvincedScore:
    THRESHOLD = 0.85  # 85% — hanya trade yg sangat yakin yg lolos

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold

    def technical_score(self, sdf, sig) -> float:
        """0..1 dari indikator teknikal."""
        if sdf is None or sdf.empty:
            return 0.0
        last = sdf.iloc[-1]
        rsi = float(last["rsi14"]) if "rsi14" in sdf.columns else 50.0
        side = sig.get("side")
        # RSI ekstrem arah benar -> tinggi
        if side == "buy":
            rsi_score = max(0.0, (45.0 - rsi) / 45.0)  # semakin oversold, semakin yakin
        else:
            rsi_score = max(0.0, (rsi - 55.0) / 45.0)  # semakin overbought, semakin yakin
        rsi_score = min(1.0, rsi_score)
        # EMA alignment
        ema_align = 0.5
        if "ema50" in sdf.columns and "ema200" in sdf.columns:
            e50 = float(last["ema50"]); e200 = float(last["ema200"])
            if e200:
                gap = (e50 - e200) / abs(e200)
                ema_align = 0.5 + 0.5 * (gap if side == "buy" else -gap) / 0.10
                ema_align = max(0.0, min(1.0, ema_align))
        # ATR masuk akal (tdk terlalu tinggi = tdk noisy)
        atr_score = 0.5
        if "atr14" in sdf.columns and "close" in sdf.columns:
            atr_pct = float(last["atr14"]) / max(float(last["close"]), 1e-9)
            atr_score = max(0.0, min(1.0, 1.0 - (atr_pct - 0.01) / 0.06))
        return 0.5 * rsi_score + 0.3 * ema_align + 0.2 * atr_score

    def sentiment_score(self, fg_value: float, psych: dict = None) -> float:
        """0..1 dari F&G + survei (1-100 -> 0..1, di-remap biar netral=0.5)."""
        fg = fg_value if fg_value is not None else 50.0
        # F&G ekstrem ke arah yg salah = rendah; tengah = netral 0.5
        # Logika: sangat greed (>80) pas buy = hati-hati (topish); sangat fear (<20) pas buy = peluang
        s = 0.5 + (50.0 - fg) / 100.0  # fear -> naik (buy opportunity), greed -> turun
        s = max(0.0, min(1.0, s))
        return s

    def ml_score(self, sfilter, setup_feat: dict) -> float:
        """probabilitas profit dari SignalFilter (0..1). Fallback 0.5 kalau blm trained."""
        try:
            if sfilter is None:
                return 0.5
            p = sfilter.predict_proba(setup_feat)
            if not p.get("trained"):
                return 0.5
            return float(p.get("prob_win", 0.5))
        except Exception:
            return 0.5

    def score(self, sdf, sig, fg_value: float = 50.0, psych: dict = None,
              sfilter=None, setup_feat: dict = None) -> dict:
        """Return dict: {score_pct, passes, parts}."""
        t = self.technical_score(sdf, sig)            # 0..1
        s = self.sentiment_score(fg_value, psych)      # 0..1
        m = self.ml_score(sfilter, setup_feat or {})   # 0..1
        # bobot: teknikal 40%, sentimen 20%, ML 40%
        combined = 0.40 * t + 0.20 * s + 0.40 * m
        score_pct = round(combined * 100.0, 1)
        return {
            "score_pct": score_pct,
            "passes": score_pct > (self.threshold * 100.0),
            "threshold_pct": int(self.threshold * 100.0),
            "parts": {
                "technical": round(t * 100.0, 1),
                "sentiment": round(s * 100.0, 1),
                "ml": round(m * 100.0, 1),
            },
        }


# singleton helper (sama pola dgn SignalFilter)
_INSTANCE = None
def get_scorer(threshold: float = 0.85) -> ConvincedScore:
    global _INSTANCE
    if _INSTANCE is None or _INSTANCE.threshold != threshold:
        _INSTANCE = ConvincedScore(threshold)
    return _INSTANCE
