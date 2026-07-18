"""
AGENT — PHOENIX (Recovery Specialist)
Spesialis pemulihan dari drawdown. Deterministik (no LLM).
  - Deteksi fase drawdown (dari equity/realized_pnl)
  - Saran recovery: turunkan ukuran, ganti ke strategi konservatif, atau
    biarkan posisi existing turnover (jangan revenge-trade)
  - Beri flag 'recovering' ke Atlas agar tim hati-hati
Output: dict {status, advice, scale}
"""
from __future__ import annotations


class Phoenix:
    def __init__(self):
        self.name = "PHOENIX"

    def assess(self, equity: float, realized_pnl: float, peak_equity: float = None) -> dict:
        peak = peak_equity if peak_equity else equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        dd_pct = dd * 100.0
        if dd_pct >= 12.0:
            status = "critical"
            advice = ("Drawdown kritis. HENTIKAN entri baru, tutup posisi marginal, "
                      "pangkas ukuran 50%, beralih ke strategi konservatif (hanya RSI oversold ekstrem).")
            scale = 0.7
        elif dd_pct >= 6.0:
            status = "recovering"
            advice = ("Fase recovery. Turunkan ukuran 25%, hindari martingale/revenge. "
                      "Biarkan posisi bagus berjalan; hanya tambah saat setup A+.")
            scale = 0.85
        elif dd_pct >= 2.0:
            status = "watch"
            advice = "Drawdown ringan. Pertahankan disiplin; jangan kompensasi kerugian dgn lot besar."
            scale = 1.0
        else:
            status = "healthy"
            advice = "Equity sehat. Mode normal."
            scale = 1.0
        return {"status": status, "dd_pct": round(dd_pct, 2),
                "advice": advice, "scale": scale}

    def recovering(self) -> bool:
        """Flag singkat untuk Atlas.decide()."""
        return False  # diisi orchestrator dari assess().status == 'recovering'
