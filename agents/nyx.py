"""
AGENT — QUEEN (Risk Guardian)
Layer teks. GUARDRAIL HARD ada di core/risk_engine.py (di-enforce di kode).
Versi upgrade: cek juga daily-loss circuit breaker status + korelasi-ringkas.
"""
from __future__ import annotations


class Nyx:
    def __init__(self):
        self.name = "QUEEN"

    def comment(self, trade_ok: bool, rr_msg: str, open_count: int, max_open: int,
                halted: bool = False, daily_loss_pct: float = 0.0) -> str:
        if halted:
            return (f"⛔ CIRCUIT BREAKER AKTIF — bot dihentikan sementara. "
                    f"Drawdown harian {daily_loss_pct:.2f}%. Jangan paksa entry.")
        if not trade_ok:
            return f"⛔ Saya TOLAK trade ini. {rr_msg} Disiplin! (R:R minimal 1:2)"
        if open_count >= max_open:
            return f"⚠️ Posisi terbuka {open_count}/{max_open}. Jangan over-leverage, istirahat dulu."
        return f"✅ Risk aman. Risk per trade 1%, R:R ok. Eksekusi dengan disiplin."
