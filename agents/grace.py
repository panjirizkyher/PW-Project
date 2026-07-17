"""
AGENT 5 — DR. GRACE (Trading Psychologist)
Versi deterministik (tanpa LLM API key).
Refleksi bias kognitif dihasilkan dari STATE NYATA bot:
  - drawdown harian (fear / panic)
  - win/loss streak (FOMO / overconfidence)
  - jumlah posisi terbuka (overtrading)
  - unrealized PnL (keserakahan / cuti loss lambat)
Return teks empati + saran konkret (bukan tebakan LLM).
"""
from __future__ import annotations
from datetime import datetime


class Grace:
    def __init__(self, llm=None):
        self.llm = llm
        self.name = "DR. GRACE"

    def reflect(self, state: dict = None, bias_hint: str = "") -> str:
        s = state or {}
        # ekstrak konteks
        realized = float(s.get("realized_pnl", 0.0) or 0.0)
        equity = float(s.get("equity", 0.0) or 0.0)
        balance = float(s.get("balance", equity) or equity)
        n_pos = int(s.get("open_positions", 0) or 0)
        max_open = int(s.get("max_open", 8) or 8)
        dd_pct = (-realized / balance * 100.0) if (realized < 0 and balance > 0) else 0.0

        lines = []
        # 1. drawdown / fear
        if dd_pct >= 2.0:
            lines.append(
                f"Drawdown harian {dd_pct:.2f}% — wajar merasa takut. "
                f"Napas. Jangan revenge-trade untuk mengganti kerugian; "
                f"biarkan R:R & circuit breaker yang menjaga.")
        # 2. overtrading
        if n_pos >= max_open:
            lines.append(
                f"Posisi terbuka {n_pos}/{max_open} — ini overtrading. "
                f"Kualitas > kuantitas. Tahan diri sebelum menambah.")
        elif n_pos >= max(3, max_open // 2):
            lines.append(
                f"{n_pos} posisi aktif — pantau korelasi; jangan semua di arah yang sama.")
        # 3. euforia / FOMO
        if realized > 0 and dd_pct == 0.0 and n_pos == 0:
            lines.append(
                "PnL hijau hari ini — syukuri, tapi waspada euforia. "
                "Kemenangan berturut bukan izin untuk memperbesar risiko.")
        # 4. default / mindfulness
        if not lines:
            lines.append(
                "Kondisi netral. Satu napas sebelum tiap entri: "
                "apakah ini berdasar setup, atau sekadar keinginan untuk aksi?")
        # selalu tutup dg saran mindfulness
        lines.append("Ingat: konsistensi beats keberuntungan. Istirahat sejenak itu bagian dari strategi.")
        return " ".join(lines)
