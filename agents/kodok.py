"""
AGENT 6 — KODOK (Execution & Coding / Signal Engine)
Menghasilkan sinyal deterministik (RSI mean-reversion) dari data nyata.
Ini yang dipakai executor untuk paper trade — bukan tebakan LLM.
"""
from __future__ import annotations
import pandas as pd
from core.indicators import rsi


class Kodok:
    def __init__(self, settings: dict):
        cfg = settings.get("signal", {})
        self.cfg = cfg
        self.name = "KODOK"
        # target R:R di atas floor hard gate (default 2.5, floor 2.0) → margin aman
        self.target_rr = float(cfg.get("target_reward_risk_ratio", 2.5))

    def generate_signal(self, df: pd.DataFrame, last_price: float) -> dict:
        """Return: {side, entry, stop_loss, take_profit, conviction} atau {}."""
        if df.empty or "rsi14" not in df.columns:
            return {}
        r = float(df.iloc[-1]["rsi14"])
        period = int(self.cfg.get("rsi_period", 14))
        ob = float(self.cfg.get("rsi_overbought", 65.0))
        os_ = float(self.cfg.get("rsi_oversold", 35.0))
        atr_like = (df["high"] - df["low"]).tail(14).mean()

        if r <= os_:
            side = "buy"
            entry = last_price
            stop_loss = entry - atr_like
            take_profit = entry + (atr_like * self.target_rr)  # target R:R buffered
            conviction = (os_ - r) / os_
        elif r >= ob:
            side = "sell"
            entry = last_price
            stop_loss = entry + atr_like
            take_profit = entry - (atr_like * self.target_rr)
            conviction = (r - ob) / (100 - ob)
        else:
            return {"side": "hold", "entry": last_price, "stop_loss": 0.0,
                    "take_profit": 0.0, "conviction": 0.0}

        return {"side": side, "entry": round(entry, 2), "stop_loss": round(stop_loss, 2),
                "take_profit": round(take_profit, 2), "conviction": round(min(max(conviction, 0), 1), 2)}
