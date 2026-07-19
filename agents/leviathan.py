"""
AGENT — SYAFIRA (Execution & Liquidity / Signal Engine)
Sinyal DETERMINISTIK dari data nyata (bukan tebakan LLM).
Strategi aktif (auto-pilih terbaik per kondisi pasar) — UPGRADE v2:
  1. TREND_FOLLOW  — beli saat EMA-fast > EMA-slow & pullback ke EMA-fast
  2. MEAN_REVERSION — beli saat RSI oversold + harga menyentuh BB lower
  3. BREAKOUT — beli saat harga tembus high N-bar (donchian)
Semua pasang SL (ATR bener) + TP (R:R target). Nyx validasi R:R>=min.
High-frequency: threshold diturunkan + multi-confirmation biar presisi.
"""
from __future__ import annotations
import pandas as pd
from core.indicators import rsi, atr, ema, bollinger


class Leviathan:
    def __init__(self, settings: dict):
        cfg = settings.get("signal", {})
        self.cfg = cfg
        self.name = "SYAFIRA"
        self.target_rr = float(cfg.get("target_reward_risk_ratio", 1.8))
        self.rsi_os = float(cfg.get("rsi_oversold", 35.0))
        self.rsi_ob = float(cfg.get("rsi_overbought", 70.0))
        self.rsi_period = int(cfg.get("rsi_period", 14))
        self.breakout_bars = int(cfg.get("breakout_bars", 12))
        self.est_fee = float(cfg.get("est_fee_pct", 0.001))  # 0.1% per side
        # high-freq: beli di zone oversold longgar (<=45), jual di overbought (>=55)
        self.rsi_os_soft = 45.0
        self.rsi_ob_soft = 55.0

    # ---------- helpers ----------
    def _atr(self, df: pd.DataFrame) -> float:
        a = atr(df, 14)
        return float(a.iloc[-1]) if a is not None and len(a) else (float((df["high"] - df["low"]).tail(14).mean()) or 0.0)

    def _ema(self, df: pd.DataFrame, period: int) -> float:
        e = ema(df["close"], period)
        return float(e.iloc[-1]) if e is not None and len(e) else float(df["close"].iloc[-1])

    def _trend_up(self, df: pd.DataFrame) -> bool:
        try:
            return self._ema(df, 50) > self._ema(df, 200)
        except Exception:
            return True

    # ---------- strategies ----------
    def _trend_signal(self, df, last) -> dict:
        """Beli saat uptrend + harga pullback ke EMA-fast (entry on dip)."""
        if not self._trend_up(df):
            return {}
        e_fast = self._ema(df, 21)
        e_slow = self._ema(df, 50)
        # entry: harga dekat/di bawah EMA-fast tapi di atas EMA-slow (pullback dlm uptrend)
        if last <= e_fast * 1.01 and last >= e_slow * 0.99:
            a = self._atr(df)
            if a <= 0:
                return {}
            side = "buy"
            stop = last - a * 1.5
            tgt = last + a * 1.5 * self.target_rr
            conv = 0.75
            return self._pack(side, last, stop, tgt, conv, "trend_follow")
        return {}

    def _reversion_signal(self, df, last) -> dict:
        r = float(df.iloc[-1]["rsi14"]) if "rsi14" in df.columns else 50.0
        # Bollinger band touch
        bb_low = float(df.iloc[-1]["bb_lower"]) if "bb_lower" in df.columns else 0.0
        bb_high = float(df.iloc[-1]["bb_upper"]) if "bb_upper" in df.columns else 0.0
        a = self._atr(df)
        if a <= 0:
            return {}
        if r <= self.rsi_os_soft and last <= bb_low * 1.005:
            stop = last - a * 1.2
            tgt = last + a * 1.2 * self.target_rr
            conv = min((self.rsi_os_soft - r) / max(self.rsi_os_soft, 1e-9), 1.0) * 0.9 + 0.1
            return self._pack("buy", last, stop, tgt, round(conv, 2), "mean_reversion")
        if r >= self.rsi_ob_soft and last >= bb_high * 0.995:
            stop = last + a * 1.2
            tgt = last - a * 1.2 * self.target_rr
            conv = min((r - self.rsi_ob_soft) / max(100 - self.rsi_ob_soft, 1e-9), 1.0) * 0.9 + 0.1
            return self._pack("sell", last, stop, tgt, round(conv, 2), "mean_reversion")
        return {}

    def _breakout_signal(self, df, last) -> dict:
        if len(df) < self.breakout_bars + 2:
            return {}
        look = df.iloc[-(self.breakout_bars + 1):-1]
        hi = float(look["high"].max())
        lo = float(look["low"].min())
        a = self._atr(df)
        if a <= 0:
            return {}
        if last > hi:
            stop = last - a * 1.0
            tgt = last + a * 1.0 * self.target_rr
            return self._pack("buy", last, stop, tgt, 0.7, "breakout")
        if last < lo:
            stop = last + a * 1.0
            tgt = last - a * 1.0 * self.target_rr
            return self._pack("sell", last, stop, tgt, 0.7, "breakout")
        return {}

    def _pack(self, side, entry, stop, tgt, conv, strat) -> dict:
        return {"side": side, "entry": round(float(entry), 2),
                "stop_loss": round(float(stop), 2),
                "take_profit": round(float(tgt), 2),
                "conviction": round(min(max(conv, 0), 1), 2),
                "strategy": strat}

    # ---------- main ----------
    def generate_signal(self, df: pd.DataFrame, last_price: float) -> dict:
        """Pilih sinyal terbaik (prioritas: trend > reversion > breakout).
        High-frequency: cari sinyal valid di semua strategi, pilih conviction tertinggi."""
        if df is None or df.empty:
            return {}
        cands = []
        for fn in (self._trend_signal, self._reversion_signal, self._breakout_signal):
            try:
                s = fn(df, last_price)
            except Exception:
                s = {}
            if s and s.get("side") in ("buy", "sell"):
                cands.append(s)
        if not cands:
            return {"side": "hold", "entry": round(float(last_price), 2),
                    "stop_loss": 0.0, "take_profit": 0.0, "conviction": 0.0}
        # pilih conviction tertinggi (presisi)
        best = max(cands, key=lambda x: x.get("conviction", 0))
        return best

    def est_cost(self, notional: float) -> float:
        """Estimasi biaya eksekusi (fee 2 sisi)."""
        return notional * 2 * self.est_fee
