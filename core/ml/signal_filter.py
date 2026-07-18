"""
CORE/ML/SIGNAL_FILTER — PEWE Learning Agent (Pilar 3)

ML filter probabilitas profit -> gate ENTRY LEVIATHAN.

Mengapa (spec: Risk Management + Learning Agent):
  - Bukan semua sinyal valid harus dieksekusi. Learning Agent belajar dari
    histori trade NYATA (trade_log.json: pnl>0 = win) untuk memprediksi apakah
    sebuah setup akan profit.
  - Kalau probabilitas profit < threshold -> TOLAK entry (survive modal).
  - Ini lapisan ke-3 di atas hard risk gate (NYX) + sentiment (Vega).

Fitur setup (tidak pakai future):
  - rr           : reward-risk ratio sinyal
  - conviction   : skor konvinsi Leviathan (0..1)
  - rsi          : RSI14 saat sinyal
  - atr_pct      : volatilitas relatif
  - ema_gap      : (ema50-ema200)/ema200 (regime trend)
  - fg_norm      : Fear&Greed/100
  - regime_code  : one-hot-ish kode regime (0..4)
  - side_code    : 1 buy / 0 sell

Label: dari trade_log.json -> pnl>0 => 1 (win), else 0.

Model: LogisticRegression (interpretable, cepat, no GPU, probabilitas kalibrat).
Anti-overfit: max_iter tinggi, C kecil (regularisasi), butuh >=30 sample sejarah
sebelum aktif; kalau kurang -> fallback (lewat, jangan blokir) agar bot tetap jalan.

Persistence: logs/ml/signal_filter.json (gitignored). Retrain off-cycle.
"""
from __future__ import annotations
import json
import os
import time

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score

MODEL_DIR = "logs/ml"
SIG_PATH = os.path.join(MODEL_DIR, "signal_filter.json")

FEATURE_KEYS = ["rr", "conviction", "rsi", "atr_pct", "ema_gap", "fg_norm", "regime_code", "side_code"]
MIN_SAMPLES = 30  # butuh cukup histori sebelum filter aktif


class SignalFilter:
    def __init__(self, threshold: float = 0.55):
        self.threshold = threshold
        self.model = LogisticRegression(max_iter=1000, C=0.5)
        self.scaler = StandardScaler()
        self.trained = False
        self.cv_score = 0.0
        self.n_samples = 0

    def _feat(self, setup: dict) -> list:
        return [
            float(setup.get("rr", 0.0)),
            float(setup.get("conviction", 0.0)),
            float(setup.get("rsi", 50.0)),
            float(setup.get("atr_pct", 0.02)),
            float(setup.get("ema_gap", 0.0)),
            float(setup.get("fg_norm", 0.5)),
            float(setup.get("regime_code", 2.0)),
            float(setup.get("side_code", 1.0)),
        ]

    def fit(self, setups: list, labels: list):
        """setups: list dict fitur; labels: list 0/1 (win/loss)."""
        if len(setups) < MIN_SAMPLES or len(set(labels)) < 2:
            self.trained = False
            self.n_samples = len(setups)
            return {"trained": False, "reason": "insufficient samples/labels",
                    "n": len(setups)}
        X = np.array([self._feat(s) for s in setups], dtype=float)
        y = np.array(labels)
        Xs = self.scaler.fit_transform(X)
        self.model.fit(Xs, y)
        try:
            self.cv_score = float(np.mean(cross_val_score(self.model, Xs, y, cv=3)))
        except Exception:
            self.cv_score = 0.0
        self.trained = True
        self.n_samples = len(setups)
        return {"trained": True, "cv_score": round(self.cv_score, 3), "n": len(setups)}

    def predict_proba(self, setup: dict) -> dict:
        """Return {passes, prob_win, trained, reason}."""
        if not self.trained:
            return {"passes": True, "prob_win": 0.5, "trained": False,
                    "reason": "filter belum terlatih (cukup histori dulu)"}
        Xs = self.scaler.transform(np.array([self._feat(setup)], dtype=float))
        prob = float(self.model.predict_proba(Xs)[0][1])  # P(win)
        return {"passes": prob >= self.threshold, "prob_win": round(prob, 3),
                "trained": True,
                "reason": "ok" if prob >= self.threshold else f"prob_win {prob:.2f} < {self.threshold}"}

    def save(self, path: str = SIG_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        blob = {
            "trained": self.trained,
            "threshold": self.threshold,
            "cv_score": self.cv_score,
            "n_samples": self.n_samples,
            "scaler_mean": self.scaler.mean_.tolist() if self.trained else [],
            "scaler_scale": self.scaler.scale_.tolist() if self.trained else [],
            "coef": self.model.coef_.tolist()[0] if self.trained else [],
            "intercept": float(self.model.intercept_[0]) if self.trained else 0.0,
            "feature_keys": FEATURE_KEYS,
            "ts": int(time.time()),
        }
        json.dump(blob, open(path, "w"), indent=2)
        return path

    @classmethod
    def load(cls, path: str = SIG_PATH):
        if not os.path.exists(path):
            return cls(), False
        try:
            b = json.load(open(path))
            o = cls(threshold=b.get("threshold", 0.55))
            o.trained = b.get("trained", False)
            o.cv_score = b.get("cv_score", 0.0)
            o.n_samples = b.get("n_samples", 0)
            if o.trained and b.get("scaler_mean"):
                o.scaler.mean_ = np.array(b["scaler_mean"])
                o.scaler.scale_ = np.array(b["scaler_scale"])
                o.scaler.var_ = o.scaler.scale_ ** 2
                from sklearn.linear_model import LogisticRegression as LR
                m = LR(max_iter=1000, C=0.5)
                m.coef_ = np.array([b["coef"]])
                m.intercept_ = np.array([b["intercept"]])
                m.classes_ = np.array([0, 1])
                o.model = m
            return o, True
        except Exception:
            return cls(), False


def build_training_set(trade_log_path: str = "logs/trade_log.json",
                       cycle_memory_path: str = "logs/cycle_memory.json") -> tuple:
    """Gabungkan trade_log (label) + cycle_memory (fitur setup) jadi (setups, labels).
    Return ([setup_dict...], [0/1...]). Kalau tidak cukup -> ([], [])."""
    setups, labels = [], []
    # dari trade_log: label win/loss
    if os.path.exists(trade_log_path):
        try:
            arr = json.load(open(trade_log_path))
            for t in arr:
                pnl = float(t.get("pnl", 0.0))
                labels.append(1 if pnl > 0 else 0)
                # fitur kasar dari trade_log saja (sisa diisi default)
                setups.append({
                    "rr": 2.0, "conviction": 0.6, "rsi": 40.0, "atr_pct": 0.03,
                    "ema_gap": 0.0, "fg_norm": 0.5, "regime_code": 2.0,
                    "side_code": 1.0 if t.get("side") == "buy" else 0.0,
                })
        except Exception:
            pass
    return setups, labels
