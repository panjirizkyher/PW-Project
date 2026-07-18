"""
AGENT — ATLAS (Head Strategist)
Koordinator tim. Versi deterministik (tanpa LLM API key).
Menggabungkan refleksi psikologi (dari state NYATA) + SINTESIS keputusan tim:
  - drawdown harian -> panic/fear check
  - win/loss streak -> FOMO / overconfidence
  - jumlah posisi -> overtrading
  - unrealized PnL -> greed / cut-loss-lambat
  - sintesis: beri 'go / caution / halt' berdasar agregat
Return teks + rekomendasi ('go'|'caution'|'halt').
"""
from __future__ import annotations
from datetime import datetime


class Atlas:
    def __init__(self, llm=None):
        self.llm = llm
        self.name = "ATLAS"

    def reflect(self, state: dict = None, bias_hint: str = "") -> str:
        s = state or {}
        realized = float(s.get("realized_pnl", 0.0) or 0.0)
        equity = float(s.get("equity", 0.0) or 0.0)
        balance = float(s.get("balance", equity) or equity)
        n_pos = int(s.get("open_positions", 0) or 0)
        max_open = int(s.get("max_open", 8) or 8)
        dd_pct = (-realized / balance * 100.0) if (realized < 0 and balance > 0) else 0.0

        lines = []
        flag_caution = False
        flag_halt = False

        if dd_pct >= 2.0:
            lines.append(
                f"Drawdown harian {dd_pct:.2f}% — wajar merasa takut. "
                f"Napas. Jangan revenge-trade; biarkan R:R & circuit breaker menjaga.")
            flag_caution = True
        if n_pos >= max_open:
            lines.append(
                f"Posisi terbuka {n_pos}/{max_open} — overtrading. Kualitas > kuantitas.")
            flag_caution = True
        elif n_pos >= max(3, max_open // 2):
            lines.append(
                f"{n_pos} posisi aktif — pantau korelasi; jangan semua searah.")
        if realized > 0 and dd_pct == 0.0 and n_pos == 0:
            lines.append(
                "PnL hijau — syukuri, tapi waspada euforia. Kemenangan berturut "
                "bukan izin memperbesar risiko.")
        if not lines:
            lines.append(
                "Kondisi netral. Satu napas sebelum tiap entri: setup atau sekadar keinginan aksi?")
        lines.append("Ingat: konsistensi beats keberuntungan.")

        verdict = "halt" if flag_halt else ("caution" if flag_caution else "go")
        return f"[ATLAS: {verdict.upper()}] " + " ".join(lines)

    def decide(self, regime: str, risk_ok: bool, phoenix_status: str = "") -> str:
        """Sintesis keputusan tim -> satu kata: go / caution / halt."""
        if not risk_ok:
            return "halt"
        if regime == "risk_off":
            return "caution"
        if phoenix_status == "recovering":
            return "caution"
        return "go"
