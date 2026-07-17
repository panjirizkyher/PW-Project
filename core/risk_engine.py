"""
RISK ENGINE — Madame Eleanor (HARD GUARDRAIL)
Semua cek di sini di-enforce di KODE, bukan cuma nasihat LLM.
LLM tidak bisa override nilai di settings.yaml.
"""
from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass
class ProposedTrade:
    symbol: str
    side: str            # "buy" | "sell"
    entry: float
    stop_loss: float
    take_profit: float
    conviction: float = 0.5  # 0..1 dari sinyal


class RiskEngine:
    def __init__(self, settings: dict):
        r = settings.get("risk", {})
        self.balance = float(r.get("account_balance", 10000.0))
        self.risk_pct = float(r.get("risk_per_trade_pct", 1.0))
        self.max_daily_loss_pct = float(r.get("max_daily_loss_pct", 3.0))
        self.min_rr = float(r.get("min_reward_risk_ratio", 2.0))
        self.max_open = int(r.get("max_open_positions", 3))
        self.max_exposure_pct = float(r.get("max_total_exposure_pct", 10.0))

    # --- validasi trade tunggal ---
    def validate(self, t: ProposedTrade) -> tuple[bool, str]:
        if t.side not in ("buy", "sell"):
            return False, "Side invalid."
        risk = abs(t.entry - t.stop_loss)
        reward = abs(t.take_profit - t.entry)
        if risk <= 0:
            return False, "Stop loss must differ from entry."
        rr = reward / risk
        if rr < self.min_rr:
            return False, f"R:R {rr:.2f} < minimum {self.min_rr:.2f} (Madame Eleanor: tolak)."
        return True, f"R:R {rr:.2f} OK."

    # --- ukuran posisi (1-2% risk) ---
    def position_size(self, t: ProposedTrade) -> float:
        risk_amt = self.balance * (self.risk_pct / 100.0)
        risk_per_unit = abs(t.entry - t.stop_loss)
        if risk_per_unit <= 0:
            return 0.0
        qty = risk_amt / risk_per_unit
        # batasi eksposur total
        max_exp_qty = (self.balance * (self.max_exposure_pct / 100.0)) / t.entry
        return min(qty, max_exp_qty)

    # --- circuit breaker: cek drawdown harian ---
    def daily_loss_breached(self, realized_pnl_today: float) -> tuple[bool, str]:
        loss_pct = (-realized_pnl_today / self.balance) * 100.0 if realized_pnl_today < 0 else 0.0
        if loss_pct >= self.max_daily_loss_pct:
            return True, (
                f"⛔ CIRCUIT BREAKER: drawdown harian {loss_pct:.2f}% >= "
                f"{self.max_daily_loss_pct:.2f}%. Bot HENTI + alert."
            )
        return False, ""

    def can_open_new(self, open_count: int) -> tuple[bool, str]:
        if open_count >= self.max_open:
            return False, f"Max open positions {self.max_open} tercapai (anti over-leverage)."
        return True, "OK"
