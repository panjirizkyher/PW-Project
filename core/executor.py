"""
EXECUTOR — layer aksi (PEWE)
- PaperExecutor : simulasi lokal, TANPA koneksi exchange.
- ExchangeExecutor : CCXT ke exchange nyata/testnet (hanya trade, TANPA withdrawal).
Posisi & equity DIKELUARKAN dari executor (disimpan di state.py) supaya
persist antar siklus & restart. Executor hanya: open / close / cek harga.
"""
from __future__ import annotations
import ccxt
from dataclasses import dataclass


@dataclass
class Fill:
    symbol: str
    side: str          # buy / sell
    qty: float
    price: float
    paper: bool
    ts: float = 0.0
    pnl: float = 0.0


class PaperExecutor:
    """Eksekusi simulasi. Harga diberikan caller (dari market data)."""
    def __init__(self):
        pass

    def execute(self, symbol, side, qty, price) -> Fill:
        import time
        return Fill(symbol, side, qty, price, paper=True, ts=time.time())

    def close(self, symbol, side, qty, price) -> Fill:
        import time
        return Fill(symbol, side, qty, price, paper=True, ts=time.time())


class ExchangeExecutor:
    """CCXT ke exchange. testnet=True => set_sandbox_mode (demo, uang virtual).

    PENTING: API key HANYA izin trading, TANPA withdrawal.
    """
    def __init__(self, exchange_id: str, api_key: str, api_secret: str, testnet: bool = True):
        cls = getattr(ccxt, exchange_id)
        self.ex = cls({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"} if exchange_id == "binance" else {},
        })
        # Binance punya sandbox testnet; exchange lain pakai testnet flag bila ada
        if testnet and hasattr(self.ex, "set_sandbox_mode"):
            try:
                self.ex.set_sandbox_mode(True)
            except Exception:
                pass
        self.testnet = testnet

    def last_price(self, symbol: str) -> float:
        return float(self.ex.fetch_ticker(symbol)["last"])

    def execute(self, symbol, side, qty, price=None) -> Fill:
        order = self.ex.create_order(symbol, "market", side, qty, None)
        fill_price = float(order.get("average") or order.get("price") or self.last_price(symbol))
        return Fill(symbol, side, qty, fill_price, paper=False)

    def close(self, symbol, side, qty, price=None) -> Fill:
        # side di sini = arah PENUTUPAN (kebalikan posisi)
        order = self.ex.create_order(symbol, "market", side, qty, None)
        fill_price = float(order.get("average") or order.get("price") or self.last_price(symbol))
        return Fill(symbol, side, qty, fill_price, paper=False)
