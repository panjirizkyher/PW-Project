"""
ACCOUNT SNAPSHOT — snapshot akun demo/testnet ke logs/account.json (PEWE).
Biar user lihat REAL TRADE di akun demo: balance, posisi/order terbuka, riwayat trade.
"""
from __future__ import annotations
import os, json


def snapshot(executor, symbols: list = None) -> dict:
    """Ambil state akun dari ExchangeExecutor (testnet). Return dict."""
    from core.executor import PaperExecutor
    out = {"mode": "paper", "balance": 0.0, "open_orders": [], "trades": [], "equity": 0.0}
    if isinstance(executor, PaperExecutor):
        # paper: cuma balance simulasi
        out["mode"] = "paper"
        os.makedirs("logs", exist_ok=True)
        with open("logs/account.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return out
    ex = getattr(executor, "ex", None)
    if ex is None:
        os.makedirs("logs", exist_ok=True)
        with open("logs/account.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return out
    try:
        bal = ex.fetch_balance()
        usdt = float(bal.get("USDT", {}).get("total", 0) or 0)
        out["mode"] = "demo"
        out["balance"] = usdt
        out["equity"] = usdt
        # open orders (cari di semua simbol ter-scan)
        syms = symbols or ["BTC/USDT"]
        orders = []
        for sym in syms:
            try:
                for o in ex.fetch_open_orders(sym):
                    orders.append({"symbol": o["symbol"], "side": o["side"],
                                    "amount": float(o["amount"]), "price": float(o.get("price") or 0)})
            except Exception:
                continue
        out["open_orders"] = orders
        # riwayat trades (terbaru)
        trades = []
        for sym in syms:
            try:
                for t in ex.fetch_my_trades(sym, limit=10):
                    trades.append({"symbol": t["symbol"], "side": t["side"],
                                   "amount": float(t["amount"]), "price": float(t["price"]),
                                   "ts": int(t.get("timestamp") or 0)})
            except Exception:
                continue
        # urut terbaru dulu, ambil 15
        trades.sort(key=lambda x: x["ts"], reverse=True)
        out["trades"] = trades[:15]
    except Exception as e:
        out["error"] = str(e)
    os.makedirs("logs", exist_ok=True)
    with open("logs/account.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out
