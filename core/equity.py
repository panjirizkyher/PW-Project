"""
EQUITY — rekam kurva nilai akun (PEWE).
Tiap tick/siklus bot tulis point {ts, equity, pnl, positions} ke logs/equity.json.
Dashboard gambar line chart + hitung PnL/Peak/MaxDD.
"""
from __future__ import annotations
import os, json


def record(equity: float, pnl: float, positions: int, ts: int = None, base_balance: float = None):
    """Tambah 1 point ke logs/equity.json (cap 3000 point).
    Jika base_balance diberi dan skala equity menyimpang >2x dari base
    (mis. sesi lama dengan balance beda / backtest tumpah ke file yg sama),
    curve di-reset otomatis supaya peak/dd konsisten dengan sesi sekarang.
    """
    if ts is None:
        import time
        ts = int(time.time())
    path = "logs/equity.json"
    os.makedirs("logs", exist_ok=True)
    arr = []
    if os.path.exists(path):
        try:
            arr = json.load(open(path))
        except Exception:
            arr = []
    # guard: reset kalau skala berubah drastis antar sesi
    if base_balance and arr:
        try:
            prev = arr[-1]["equity"]
            if prev > 0 and (equity / prev > 2.0 or prev / equity > 2.0):
                # skala beda >2x -> anggap sesi baru, mulai bersih
                arr = []
        except Exception:
            pass
    arr.append({"ts": ts, "equity": round(float(equity), 2),
                "pnl": round(float(pnl), 2), "positions": int(positions)})
    if len(arr) > 3000:
        arr = arr[-3000:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(arr, f)


def load() -> list:
    try:
        return json.load(open("logs/equity.json"))
    except Exception:
        return []


def stats(arr: list) -> dict:
    if not arr:
        return {"pnl": 0.0, "peak": 0.0, "max_dd": 0.0, "points": 0}
    eq = [p["equity"] for p in arr]
    peak = max(eq)
    dd = 0.0
    run = eq[0]
    for v in eq:
        run = max(run, v)
        dd = min(dd, v - run)
    first = eq[0]
    last = eq[-1]
    return {
        "pnl": round(last - first, 2),
        "peak": round(peak, 2),
        "max_dd": round(dd, 2),
        "points": len(arr),
    }
