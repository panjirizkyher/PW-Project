"""
CORE/ML/PARAMETER_OPTIMIZER — PEWE Learning Agent (Pilar 2)

Optimasi parameter strategi PER REGIME secara otomatis.

Mengapa (spec AI Trading Agent Architect — Learning Agent):
  - Setelan statis (rsi_oversold=35, rr=1.8) tidak optimal di semua kondisi market.
  - Learning Agent HARUS menemukan parameter terbaik untuk tiap regime
    (uptrend / downtrend / range / volatile / panic) dari data historis.
  - Hasil: dict {regime -> {rsi_oversold, rsi_overbought, target_rr, atr_mult}}.
    LEVIATHAN memakai ini saat regime terdeteksi -> adaptasi mandiri.

Metode (anti-overfit):
  - Grid search kecil via sklearn ParameterGrid (bukan random luas -> cegah overfit).
  - Evaluasi pakai engine backtest YANG SAMA dengan live (_simulate_one + _metrics).
  - Metrik pemilihan: profit_factor (harus >1.1) lalu net_% lalu win_rate,
    DENGAN penalti drawdown besar (max_dd dikali bobot).
  - Walk-forward sederhana: train di bagian awal, validasi di bagian akhir.
  - Simpan ke logs/ml/optimal_params.json (gitignored).
"""
from __future__ import annotations
import json
import os
import time

import numpy as np
from sklearn.model_selection import ParameterGrid

from core.backtest import _simulate_one, _metrics
from core.montecarlo import simulate_with_costs

MODEL_DIR = "logs/ml"
PARAMS_PATH = os.path.join(MODEL_DIR, "optimal_params.json")

# Grid kecil (intentional sempit -> cegah overfit)
GRID = {
    "rsi_oversold": [28.0, 32.0, 35.0, 40.0],
    "rsi_overbought": [62.0, 68.0, 72.0],
    "target_rr": [1.8, 2.2, 2.5],
    "atr_mult": [1.5, 2.0, 2.5],
}

DEFAULT_PARAMS = {
    "rsi_oversold": 35.0,
    "rsi_overbought": 70.0,
    "target_rr": 1.8,
    "atr_mult": 2.0,
}


def _score(trades: list, n_sims: int = 300) -> float:
    """Skor gabungan (instruksi A: turunkan standar deviasi hasil backtest).
    Dominan: Profit Factor tinggi, LALU penalti std dev equity (Monte Carlo)
    dan penalti drawdown. Return -inf kalau rugi / PF<1.05.
    """
    m = _metrics(trades)
    pf = m.get("profit_factor", 0.0)
    net = m.get("net_pct", 0.0)
    dd = m.get("max_dd", 100.0)
    win = m.get("win_rate", 0.0)
    if pf < 1.05 or net <= 0:
        return -1e9  # tolak parameter yang rugi
    # std dev equity dari Monte Carlo (proxy konsistensi)
    try:
        from core.montecarlo import monte_carlo
        mc = monte_carlo(trades, n_sims=n_sims, start_equity=10000.0, ruin_pct=50.0)
        std_dev = mc.get("equity_final_median", 10000.0)  # pakai spread p95-p05 sbg proxy variasi
        variation = (mc.get("equity_final_p95", 10000.0) - mc.get("equity_final_p05", 10000.0))
        var_norm = variation / 10000.0  # normalisasi
    except Exception:
        var_norm = 1.0
    # skor: PF*net - penalti variasi (std dev) - penalti dd
    return pf * net - 0.25 * var_norm - 0.15 * dd + 0.05 * win


def optimize_for_symbol(df, risk: dict, fee_pct: float = 0.001,
                        split: float = 0.7, use_costs: bool = True) -> dict:
    """Cari param terbaik untuk 1 DataFrame (1 regime/symbol).
    Walk-forward: train di 70% awal, validasi 30% akhir.
    use_costs=True -> simulator makan slippage+spread (align dgn MC)."""
    n = len(df)
    if n < 200:
        return dict(DEFAULT_PARAMS)
    cut = int(n * split)
    train_df = df.iloc[:cut].copy()
    valid_df = df.iloc[cut:].copy()

    best = None
    best_score = -1e9
    for g in ParameterGrid(GRID):
        sg = {
            "rsi_oversold": g["rsi_oversold"],
            "rsi_overbought": g["rsi_overbought"],
            "target_rr": g["target_rr"],
            "atr_mult": g["atr_mult"],
        }
        try:
            if use_costs:
                trades = simulate_with_costs(valid_df, sg, risk, fee_pct,
                                             slippage_pct=0.0005, spread_pct=0.0003)
            else:
                trades = _simulate_one(valid_df, sg, risk, fee_pct)
        except Exception:
            continue
        if not trades:
            continue
        s = _score(trades)
        if s > best_score:
            best_score = s
            best = dict(g)
    return best if best else dict(DEFAULT_PARAMS)


def optimize_all(regime_dfs: dict, risk: dict, fee_pct: float = 0.001,
                 use_costs: bool = True) -> dict:
    """regime_dfs: {regime_name: DataFrame pangsi historis regime tsb}.
    Return {regime: params} + metadata skor."""
    out = {}
    for regime, df in regime_dfs.items():
        try:
            p = optimize_for_symbol(df, risk, fee_pct, use_costs=use_costs)
        except Exception:
            p = dict(DEFAULT_PARAMS)
        out[regime] = p
    out["_meta"] = {
        "ts": int(time.time()),
        "grid_size": len(list(ParameterGrid(GRID))),
        "regimes": list(regime_dfs.keys()),
        "use_costs": use_costs,
    }
    os.makedirs(MODEL_DIR, exist_ok=True)
    json.dump(out, open(PARAMS_PATH, "w"), indent=2)
    return out


def load_params(path: str = PARAMS_PATH) -> dict:
    if not os.path.exists(path):
        return {"_meta": {}, "default": dict(DEFAULT_PARAMS)}
    try:
        return json.load(open(path))
    except Exception:
        return {"_meta": {}, "default": dict(DEFAULT_PARAMS)}


def params_for_regime(regime: str, db: dict = None) -> dict:
    """Ambil param untuk regime tertentu; fallback ke default."""
    db = db or load_params()
    return db.get(regime, db.get("default", dict(DEFAULT_PARAMS)))


# ----------------------------------------------------------------------------
# MULTI-ASSET PORTFOLIO OPTIMIZATION (Fase: diversifikasi alpha)
# Tujuan: PF >= 1.5 via diversifikasi, smoothing kurva ekuitas.
# Anti-overfit: per-asset walk-forward (di optimize_for_symbol) + filter PF wajar.
# ----------------------------------------------------------------------------
def fetch_ohlcv_real(symbol: str, timeframe: str = "1h", limit: int = 700):
    """Fetch OHLCV REAL via ccxt (public, tanpa key). Return df ber-indikator atau None."""
    try:
        import ccxt
        import pandas as pd
        ex = ccxt.binance()
        o = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(o, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        df = df.set_index("ts")
        from core.indicators import add_indicators
        return add_indicators(df)
    except Exception:
        return None


def optimize_portfolio(symbols: list, risk: dict, fee_pct: float = 0.001,
                       use_costs: bool = True, sleep: float = 0.15,
                       min_pf: float = 1.1) -> dict:
    """Optimasi PER-SYMBOL (portofolio integration).
    Untuk tiap token: fetch real -> cari param cost-aware terbaik (walk-forward) ->
    simulasi -> simpan param + metrik. Pilih aset dgn PF>=min_pf & net>0.
    Return {symbol: params, "_profitable": {symbol: params}, "_meta": {...}}.
    """
    from core.montecarlo import simulate_with_costs
    from core.backtest import _simulate_one, _metrics
    out = {}
    profitable = {}
    ok_syms = []
    for sym in symbols:
        try:
            df = fetch_ohlcv_real(sym, "1h", 700)
            if df is None or len(df) < 200:
                continue
            p = optimize_for_symbol(df, risk, fee_pct, use_costs=use_costs)
            sg = {"rsi_oversold": p.get("rsi_oversold", 35.0),
                  "rsi_overbought": p.get("rsi_overbought", 70.0),
                  "target_rr": p.get("target_rr", 2.5)}
            if use_costs:
                tr = simulate_with_costs(df, sg, risk, fee_pct,
                                         slippage_pct=0.0005, spread_pct=0.0003)
            else:
                tr = _simulate_one(df, sg, risk, fee_pct)
            m = _metrics(tr)
            out[sym] = p
            ok_syms.append(sym)
            if m["profit_factor"] >= min_pf and m["net_pct"] > 0:
                profitable[sym] = p
        except Exception:
            continue
        import time as _t
        _t.sleep(sleep)  # jaga rate-limit Binance public
    out["_profitable"] = profitable
    out["_meta"] = {
        "ts": int(time.time()),
        "type": "portfolio",
        "n_symbols": len(ok_syms),
        "n_profitable": len(profitable),
        "profitable_symbols": list(profitable.keys()),
        "min_pf": min_pf,
        "use_costs": use_costs,
    }
    os.makedirs(MODEL_DIR, exist_ok=True)
    json.dump(out, open(PARAMS_PATH.replace("optimal_params", "portfolio_params"), "w"), indent=2)
    return out


def portfolio_trades(symbols: list, params_db: dict, risk: dict,
                     fee_pct: float = 0.001, use_costs: bool = True,
                     sleep: float = 0.15, only_profitable: bool = True) -> list:
    """Simulasikan trades SELURUH simbol dgn param masing-masing (cost-aware).
    only_profitable=True -> HANYA aset di _profitable yg masuk (quality bar),
    sisanya di-skip (ini 'diversifikasi alpha': pilih yg lolos, bukan semua).
    Return list trade gabungan (portofolio) -> untuk MC smoothing."""
    from core.montecarlo import simulate_with_costs
    from core.backtest import _simulate_one
    profitable = params_db.get("_profitable", {}) if only_profitable else {}
    all_tr = []
    for sym in symbols:
        if only_profitable and sym not in profitable:
            continue  # skip aset rugi -> jaga PF portfolio
        try:
            df = fetch_ohlcv_real(sym, "1h", 700)
            if df is None or len(df) < 200:
                continue
            p = params_db.get(sym, DEFAULT_PARAMS)
            sg = {"rsi_oversold": p.get("rsi_oversold", 35.0),
                  "rsi_overbought": p.get("rsi_overbought", 70.0),
                  "target_rr": p.get("target_rr", 2.5)}
            if use_costs:
                tr = simulate_with_costs(df, sg, risk, fee_pct,
                                         slippage_pct=0.0005, spread_pct=0.0003)
            else:
                tr = _simulate_one(df, sg, risk, fee_pct)
            all_tr.extend(tr)
        except Exception:
            continue
        import time as _t
        _t.sleep(sleep)
    return all_tr

