"""
AGENT 3 — MADAME ELEANOR (Risk Manager)
Layer teks. GUARDRAIL HARD ada di core/risk_engine.py (di-enforce di kode).
"""
from __future__ import annotations


class Eleanor:
    def __init__(self):
        self.name = "MADAME ELEANOR"

    def comment(self, trade_ok: bool, rr_msg: str, open_count: int, max_open: int) -> str:
        if not trade_ok:
            return f"⛔ Saya TOLAK trade ini. {rr_msg} Disiplin, Nak! (R:R minimal 1:2)"
        if open_count >= max_open:
            return f"⚠️ Posisi terbuka sudah {open_count}/{max_open}. Jangan over-leverage, istirahat dulu."
        return f"✅ Risk aman. Risk per trade 1%, R:R ok. Eksekusi dengan disiplin."
