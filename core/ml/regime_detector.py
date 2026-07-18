"""
CORE/ML/REGIME_DETECTOR — PEWE Learning Agent (Pilar 1)

Market Regime Detection via unsupervised clustering + supervised classifier.

Tujuan (sesuai spec PEWE / AI Trading Agent Architect):
  - Mengklasifikasi kondisi market secara mandiri (trending up/down,
    sideways/range, volatile/breakout, panic/crash).
  - Output regime dipakai oleh Strategy Agent (LEVIATHAN) untuk memilih
    parameter strategi terbaik per kondisi (bukan satu setelan statis).

Pendekatan (CTO decision — scikit-learn cukup, NO overfit):
  - Fitur: volatilitas (ATR/price), retrace EMA50-EMA200, RSI, slope EMA,
    adv-dec ratio dari screener (breadth), Fear&Greed, BTC dominance delta.
  - Clustering: MiniBatchKMeans (cepat, streaming-friendly) untuk menemukan
    "cluster alami" regime dari histori.
  - Labelling: tiap cluster di-label otomatis dari karakteristiknya
    (mean volatilitas + mean trend slope) -> human-readable regime name.
  - Classifier (produksi): KNeighborsClassifier / GaussianNB yang memetakan
    fitur LIVE ke regime label (ringan, no GPU, deterministic).
  - Persistence: model + label map disimpan ke logs/ml/regime_model.json
    (gitignored). Retrain off-cycle dari state historis.

Anti-overfit guards:
  - TIDAK pakai future data (hanya fitur t->t).
  - Jumlah cluster kecil (3-5).
  - Classifier dievaluasi dengan cross_val_score sebelum dipakai.
"""
from __future__ import annotations
import json
import os
import time

import numpy as np

# sklearn sudah terpasang di .venv (1.9.0)
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import MiniBatchKMeans
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import cross_val_score
from sklearn.metrics import silhouette_score

MODEL_DIR = "logs/ml"
MODEL_PATH = os.path.join(MODEL_DIR, "regime_model.json")

# Nama regime yang readable (mapping dari karakteristik cluster)
REGIME_NAMES = {
    "trend_up": "UPTREND",
    "trend_down": "DOWNTREND",
    "range": "RANGE/SIDEWAYS",
    "volatile": "VOLATILE/BREAKOUT",
    "panic": "PANIC/CRASH",
}


def _feat_row(df, fg_value=None, breadth=None, dom_delta=None) -> list:
    """Ekstrak fitur regime dari 1 DataFrame OHLCV (sudah add_indicators).

    df butuh kolom: close, atr14, ema50, ema200, rsi14.
    Return list[float] (7 fitur) atau None kalau data kurang.
    """
    try:
        if df is None or len(df) < 50:
            return None
        close = df["close"].astype(float)
        atr = df["atr14"].astype(float) if "atr14" in df else (df["high"] - df["low"]).rolling(14).mean()
        ema50 = df["ema50"].astype(float) if "ema50" in df else close.rolling(50).mean()
        ema200 = df["ema200"].astype(float) if "ema200" in df else close.rolling(200).mean()
        rsi = df["rsi14"].astype(float) if "rsi14" in df else (close.diff().rolling(14).apply(
            lambda x: 100 - 100 / (1 + (x[x > 0].sum() / max(abs(x[x < 0].sum()), 1e-9))), raw=False))

        last = -1
        vol = float(atr.iloc[last] / close.iloc[last]) if close.iloc[last] else 0.0  # ATR% harga
        trend_slope = float((ema50.iloc[last] - ema200.iloc[last]) / max(ema200.iloc[last], 1e-9))  # % gap EMA
        rsi_v = float(rsi.iloc[last]) if not np.isnan(rsi.iloc[last]) else 50.0
        ret_20 = float(close.iloc[last] / max(close.iloc[-20], 1e-9) - 1.0)  # return 20 bar
        fg = float(fg_value) if fg_value is not None else 50.0
        br = float(breadth) if breadth is not None else 0.5
        dom = float(dom_delta) if dom_delta is not None else 0.0
        return [vol, trend_slope, rsi_v, ret_20, fg / 100.0, br, dom]
    except Exception:
        return None


class RegimeDetector:
    def __init__(self, n_clusters: int = 4):
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.kmeans = None
        self.classifier = KNeighborsClassifier(n_neighbors=5)
        self.label_map = {}      # cluster_id -> regime_name
        self.trained = False
        self.cv_score = 0.0
        self.silhouette = 0.0

    # ---- training ----
    def fit(self, feature_rows: list):
        """Training dari list of feature rows (historis). Unsupervised + labelling."""
        X = np.array([r for r in feature_rows if r is not None], dtype=float)
        if len(X) < self.n_clusters * 3:
            raise ValueError(f"Data tidak cukup untuk cluster ({len(X)} < {self.n_clusters*3})")
        Xs = self.scaler.fit_transform(X)
        self.kmeans = MiniBatchKMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        clusters = self.kmeans.fit_predict(Xs)
        # silhouette (kualitas cluster, -1..1; >0.25 sudah oke)
        try:
            self.silhouette = float(silhouette_score(Xs, clusters))
        except Exception:
            self.silhouette = 0.0
        # label tiap cluster dari karakteristik mean
        self.label_map = self._auto_label(X, clusters)
        # supervised classifier: fitur -> regime label (untuk produksi live)
        y = np.array([self.label_map[int(c)] for c in clusters])
        self.classifier.fit(Xs, y)
        # evaluasi generalisasi (cross-val) — guard overfit
        try:
            self.cv_score = float(np.mean(cross_val_score(self.classifier, Xs, y, cv=3)))
        except Exception:
            self.cv_score = 0.0
        self.trained = True
        return self._summary()

    def _auto_label(self, X, clusters) -> dict:
        """Label cluster berdasar mean volatilitas + mean trend slope."""
        out = {}
        for c in range(self.n_clusters):
            mask = clusters == c
            if mask.sum() == 0:
                out[c] = "range"
                continue
            vol = X[mask, 0].mean()
            slope = X[mask, 1].mean()
            fg = X[mask, 4].mean() * 100
            if fg < 20:
                out[c] = "panic"
            elif vol > 0.04:  # ATR% > 4% = volatile
                out[c] = "volatile"
            elif slope > 0.02:
                out[c] = "trend_up"
            elif slope < -0.02:
                out[c] = "trend_down"
            else:
                out[c] = "range"
        return out

    # ---- prediksi produksi ----
    def predict(self, feature_row: list) -> dict:
        """Prediksi regime dari 1 baris fitur LIVE.
        Return {regime, label, confidence, trained}."""
        if not self.trained or feature_row is None:
            return {"regime": "range", "label": REGIME_NAMES["range"],
                    "confidence": 0.0, "trained": False}
        Xs = self.scaler.transform(np.array([feature_row], dtype=float))
        reg = self.classifier.predict(Xs)[0]
        # confidence = jarak ke tetangga terdekat (1/(1+dist))
        dist, _ = self.classifier.kneighbors(Xs)
        conf = float(1.0 / (1.0 + dist[0].mean()))
        return {"regime": reg, "label": REGIME_NAMES.get(reg, reg.upper()),
                "confidence": round(conf, 3), "trained": True}

    def _summary(self) -> dict:
        return {
            "trained": self.trained,
            "n_clusters": self.n_clusters,
            "label_map": self.label_map,
            "cv_score": round(self.cv_score, 3),
            "silhouette": round(self.silhouette, 3),
        }

    # ---- persistence (joblib untuk objek sklearn, json untuk metadata) ----
    def save(self, path: str = MODEL_PATH):
        import joblib
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # simpan objek sklearn (scaler, kmeans, classifier) ke .joblib
        joblib.dump({"scaler": self.scaler, "kmeans": self.kmeans,
                     "classifier": self.classifier}, path)
        # metadata ringan ke .json (dibaca orchestrator/PHOENIX tanpa load model)
        meta = {
            "trained": self.trained,
            "n_clusters": self.n_clusters,
            "label_map": {str(k): v for k, v in self.label_map.items()},
            "cv_score": round(self.cv_score, 3),
            "silhouette": round(self.silhouette, 3),
            "ts": int(time.time()),
            "joblib": os.path.basename(path),
        }
        json.dump(meta, open(path.replace(".json", "_meta.json"), "w"), indent=2)
        return path

    @classmethod
    def load(cls, path: str = MODEL_PATH):
        import joblib
        if not os.path.exists(path):
            return cls(), False
        try:
            bundle = joblib.load(path)
            obj = cls(n_clusters=bundle["kmeans"].n_clusters if bundle.get("kmeans") else 4)
            obj.trained = True
            obj.scaler = bundle["scaler"]
            obj.kmeans = bundle["kmeans"]
            obj.classifier = bundle["classifier"]
            # label_map dari meta json (atau rebuild dari kmeans kalau hilang)
            meta_path = path.replace(".json", "_meta.json")
            if os.path.exists(meta_path):
                meta = json.load(open(meta_path))
                obj.label_map = {int(k): v for k, v in meta.get("label_map", {}).items()}
                obj.cv_score = meta.get("cv_score", 0.0)
                obj.silhouette = meta.get("silhouette", 0.0)
            return obj, True
        except Exception:
            return cls(), False


# ---- (serializer JSON manual dihapus: gunakan joblib, standard & robust) ----

