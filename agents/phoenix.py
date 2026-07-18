"""
AGENT — PHOENIX (Recovery Specialist + LEARNING AGENT ML)

Upgrade: PHOENIX sekarang juga bertindak sebagai Learning Agent pusat.
  - assess(): recovery berbasis DD (tetap ada, deterministik).
  - learn(): retrain ML models dari histori (regime_detector + signal_filter)
    dan laporkan status adaptasi ke Atlas.

Mengapa (spec AI Trading Agent Architect — Learning Agent):
  - Sistem harus belajar dari hasil trading & adaptasi terhadap perubahan market.
  - PHOENIX menjalankan retrain OFF-CYCLE (tidak di run_structured tiap tick)
    via method learn(), dipanggil oleh orchestrator tiap N cycle / manual.
  - Tidak pernah crash pipeline utama: semua try/except, fallback aman.

Output learn(): dict {regime_trained, filter_trained, cv, n_trades, note}
"""
from __future__ import annotations
import os
import json

# ML modules
from core.ml.regime_detector import RegimeDetector, _feat_row
from core.ml.signal_filter import SignalFilter, build_training_set
from core.ml.parameter_optimizer import optimize_all, DEFAULT_PARAMS


class Phoenix:
    def __init__(self):
        self.name = "PHOENIX"

    # ---------- Recovery (deterministik, tetap ada) ----------
    def assess(self, equity: float, realized_pnl: float, peak_equity: float = None) -> dict:
        peak = peak_equity if peak_equity else equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        dd_pct = dd * 100.0
        if dd_pct >= 12.0:
            status = "critical"; scale = 0.7
            advice = ("Drawdown kritis. HENTIKAN entri baru, tutup posisi marginal, "
                      "pangkas ukuran 50%, beralih ke strategi konservatif.")
        elif dd_pct >= 6.0:
            status = "recovering"; scale = 0.85
            advice = "Fase recovery. Turunkan ukuran 25%, hindari martingale/revenge."
        elif dd_pct >= 2.0:
            status = "watch"; scale = 1.0
            advice = "Drawdown ringan. Pertahankan disiplin; jangan kompensasi dgn lot besar."
        else:
            status = "healthy"; scale = 1.0
            advice = "Equity sehat. Mode normal."
        return {"status": status, "dd_pct": round(dd_pct, 2),
                "advice": advice, "scale": scale}

    def recovering(self) -> bool:
        return False

    # ---------- Learning Agent (ML retrain) ----------
    def learn(self, feature_rows: list = None, regime_dfs: dict = None,
              trade_log_path: str = "logs/trade_log.json") -> dict:
        """Retrain ML models dari histori. Return status ringkas.
        feature_rows: list fitur regime (dari screener/ohlcv historis).
        regime_dfs: {regime: DataFrame} utk optimasi param.
        trade_log: label win/loss utk signal_filter.
        """
        note = []
        # 1) Regime detector
        reg_trained = False
        if feature_rows:
            try:
                rd = RegimeDetector(n_clusters=4)
                summ = rd.fit(feature_rows)
                rd.save()
                reg_trained = summ.get("trained", False)
                note.append(f"regime cv={summ.get('cv_score')} sil={summ.get('silhouette')}")
            except Exception as e:
                note.append(f"regime gagal: {e}")
        # 2) Signal filter (dari trade_log nyata)
        filt_trained = False
        try:
            setups, labels = build_training_set(trade_log_path)
            sf = SignalFilter(threshold=0.55)
            res = sf.fit(setups, labels)
            if res.get("trained"):
                sf.save()
                filt_trained = True
                note.append(f"filter cv={res.get('cv_score')} n={res.get('n')}")
            else:
                note.append(f"filter belum aktif: {res.get('reason')}")
        except Exception as e:
            note.append(f"filter gagal: {e}")
        # 3) Parameter optimizer per regime
        opt_done = False
        if regime_dfs:
            try:
                risk = self._risk_stub()
                optimize_all(regime_dfs, risk)
                opt_done = True
                note.append("param optimizer: selesai")
            except Exception as e:
                note.append(f"optimizer gagal: {e}")
        return {
            "learning": True,
            "regime_trained": reg_trained,
            "filter_trained": filt_trained,
            "optimizer_done": opt_done,
            "n_trades": len(setups) if 'setups' in dir() else 0,
            "note": "; ".join(note) or "tidak ada data histori cukup",
        }

    def _risk_stub(self) -> dict:
        """Stub risk setting untuk optimizer (konsisten dgn settings.yaml live)."""
        try:
            import yaml
            s = yaml.safe_load(open("config/settings.yaml"))
            return s.get("risk", {})
        except Exception:
            return {"risk_per_trade_pct": 8.0, "min_reward_risk_ratio": 1.8}

    # ---------- Runtime helper: ambil param untuk regime saat ini ----------
    def best_params_for(self, regime: str) -> dict:
        from core.ml.parameter_optimizer import params_for_regime, load_params
        return params_for_regime(regime, load_params())

    def filter_signal(self, setup: dict) -> dict:
        from core.ml.signal_filter import SignalFilter
        sf, _ = SignalFilter.load()
        return sf.predict_proba(setup)
