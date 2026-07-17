"""
EXECUTOR — paper (default) & live (testnet/real).
Paper: simulasi lokal, tidak ada network ke exchange.
Live: via CCXT, HANYA jika settings.mode=="live" DAN confirm_live_manually.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Fill:
    symbol: str
    side: str
    qty: float
    price: float
    ts: float
    paper: bool
    pnl: float = 0.0


class PaperExecutor:
    """Simulasi eksekusi lokal. Menyimpan posisi & PnL sederhana."""
    def __init__(self, starting_balance: float = 10000.0):
        self.balance = starting_balance
        self.positions: list[dict] = []

    def execute(self, symbol, side, qty, price) -> Fill:
        # simulasi: catat posisi; PnL dihitung saat close (lihat close_position)
        pos = {"symbol": symbol, "side": side, "qty": qty, "entry": price, "ts": time.time()}
        self.positions.append(pos)
        return Fill(symbol, side, qty, price, time.time(), paper=True)

    def close_position(self, pos_idx: int, exit_price: float) -> Fill:
        pos = self.positions.pop(pos_idx)
        if pos["side"] == "buy":
            pnl = (exit_price - pos["entry"]) * pos["qty"]
        else:
            pnl = (pos["entry"] - exit_price) * pos["qty"]
        self.balance += pnl
        return Fill(pos["symbol"], pos["side"], pos["qty"], exit_price, time.time(), paper=True, pnl=pnl)


class LiveExecutor:
    """CCXT live/testnet. TIDAK dijalankan kecuali di-confirm di settings."""
    def __init__(self, exchange_id: str, api_key: str, api_secret: str, testnet: bool):
        import ccxt
        cls = getattr(ccxt, exchange_id)
        self.ex = cls({"apiKey": api_key, "secret": api_secret, "enableRateLimit": True})
        if testnet and hasattr(self.ex, "set_sandbox_mode"):
            self.ex.set_sandbox_mode(True)

    def execute(self, symbol, side, qty, price):
        # market order (trade-only key, tanpa withdrawal)
        order = self.ex.create_order(symbol, "market", side, qty, None)
        return Fill(symbol, side, qty, price, time.time(), paper=False)
