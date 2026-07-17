"""
STATE — persistensi antar siklus (PEWE)
Simpan posisi terbuka + equity ke file JSON agar bot tetap tahu posisi
meski di-restart. Tanpa ini, bot lupa posisi tiap siklus.
"""
from __future__ import annotations
import json
import os
from datetime import datetime


def _default_state_path() -> str:
    os.makedirs("logs", exist_ok=True)
    return "logs/state.json"


def load_state(path: str = None) -> dict:
    path = path or _default_state_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "equity": None,          # diisi saat init (paper) atau dari exchange (real)
        "positions": [],         # list posisi terbuka
        "realized_pnl": 0.0,     # akumulasi PnL tertutup hari ini
        "day": str(datetime.now().date()),
        "updated": None,
    }


def save_state(state: dict, path: str = None):
    path = path or _default_state_path()
    state["updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def reset_day_if_new(state: dict) -> dict:
    """Reset realized_pnl tiap hari baru (untuk circuit breaker harian)."""
    today = str(datetime.now().date())
    if state.get("day") != today:
        state["day"] = today
        state["realized_pnl"] = 0.0
    return state
