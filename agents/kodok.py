"""
AGENT 6 — KODOK (Execution & Coding / Signal Engine)
Sinyal DETERMINISTIK dari data nyata (bukan tebakan LLM).
Dua strategi aktif (auto-pilih terbaik per kondisi pasar):
  1. RSI_MEAN_REVERSION — beli saat oversold / jual saat overbought
  2. BREAKOUT — beli saat harga tembus high N-bar / jual saat tembus low
Kedua selalu pasang SL (ATR) + TP (R:R target). Eleanor (risk gate)
validasi R:R >= floor sebelum eksekusi.
"""
from __future__ import annotations
import pandas as pd
from core.indicators import rsi


class Kodok:
    def __init__(self, settings: dict):
        cfg = settings.get("signal", {})
        self.cfg = cfg
        self.name = "KODOK"
        self.target_rr = float(cfg.get("target_reward_risk_ratio", 2.5))
        self.rsi_os = float(cfg.get("rsi_oversold", 35.0))
        self.rsi_ob = float(cfg.get("rsi_overbought", 65.0))
        self.rsi_period = int(cfg.get("rsi_period", 14))
        self.breakout_bars = int(cfg.get("breakout_bars", 20))

    # ---- strategi 1: RSI mean-reversion ----
    def _rsi_signal(self, df: pd.DataFrame, last: float) -> dict:
        if "rsi14" not in df.columns:
            return {}
        r = float(df.iloc[-1]["rsi14"])
        atr = (df["high"] - df["low"]).tail(self.rsi_period).mean()
        if r <= self.rsi_os:
            side = "buy"
            entry = last
            stop = entry - atr
            tgt = entry + atr * self.target_rr
            conv = (self.rsi_os - r) / max(self.rsi_os, 1e-9)
        elif r >= self.rsi_ob:
            side = "sell"
            entry = last
            stop = entry + atr
            tgt = entry - atr * self.target_rr
            conv = (r - self.rsi_ob) / max(100 - self.rsi_ob, 1e-9)
        else:
            return {"side": "hold"}
        return {"side": side, "entry": round(entry, 2), "stop_loss": round(stop, 2),
                "take_profit": round(tgt, 2), "conviction": round(min(max(conv, 0), 1), 2),
                "strategy": "rsi_reversion"}

    # ---- strategi 2: breakout ----
    def _breakout_signal(self, df: pd.DataFrame, last: float) -> dict:
        if len(df) < self.breakout_bars + 2:
            return {}
        look = df.iloc[-(self.breakout_bars + 1):-1]
        hi = float(look["high"].max())
        lo = float(look["low"].min())
        atr = (df["high"] - df["low"]).tail(self.rsi_period).mean()
        # beli bila tutup tembus high; jual bila tembus low
        if last > hi:
            side = "buy"; stop = last - atr; tgt = last + atr * self.target_rr
            conv = 0.7
        elif last < lo:
            side = "sell"; stop = last + atr; tgt = last - atr * self.target_rr
            conv = 0.7
        else:
            return {"side": "hold"}
        return {"side": side, "entry": round(last, 2), "stop_loss": round(stop, 2),
                "take_profit": round(tgt, 2), "conviction": round(conv, 2),
                "strategy": "breakout"}

    def generate_signal(self, df: pd.DataFrame, last_price: float) -> dict:
        """Pilih sinyal terbaik (prioritas breakout bila ada, else RSI)."""
        if df is None or df.empty:
            return {}
        brk = self._breakout_signal(df, last_price)
        if brk and brk.get("side") in ("buy", "sell"):
            return brk
        rev = self._rsi_signal(df, last_price)
        if rev and rev.get("side") in ("buy", "sell"):
            return rev
        # hold
        return {"side": "hold", "entry": round(last_price, 2), "stop_loss": 0.0,
                "take_profit": 0.0, "conviction": 0.0}
