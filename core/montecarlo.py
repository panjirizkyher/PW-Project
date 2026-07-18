"""
CORE/MONTECARLO — PEWE (Evaluasi Statistik Nyata)

Mengapa (prinsip #1 PEWE: SURVIVAL MODAL + konsistensi, bukan janji profit):
  - 1 jalur backtest bisa kelihatan profitabel tapi rapuh (luck).
  - Monte Carlo jawab: "Seberapa mungkin strategy ini RUGI / RUIN / PROFIT
    kalau urutan & ukuran trade diacak?" -> distribusi outcome, bukan 1 angka.
  - Slippage + spread dimodelkan -> net realistis (backtest lama terlalu optimis).
  - Walk-forward -> cek strategi tetap profitable di data di LUAR sample training.

3 fitur:
  1. simulate_with_costs(): simulator yg makan slippage + spread + fee.
  2. monte_carlo(): bootstrap urutan trade -> distribusi equity + P(ruin) + CI.
  3. walk_forward(): split histori jadi folds, backtest tiap fold.

Semua anti-overfit: bootstrap pakai reseed, slippage konservatif (bisa di-set).
"""
from __future__ import annotations
import numpy as np
from core.backtest import _simulate_one, _metrics


# ---------- 1. SIMULATOR DENGAN SLIPPAGE + SPREAD ----------
def simulate_with_costs(df, sg: dict, risk: dict,
                         fee_pct: float = 0.001,
                         slippage_pct: float = 0.0005,
                         spread_pct: float = 0.0003) -> list:
    """Sama seperti _simulate_one tapi entry kena SLIPPAGE + SPREAD.
    - BUY entry  = price * (1 + slippage + spread/2)
    - SELL entry = price * (1 - slippage - spread/2)
    - SL/TP dihitung dari entry REAL (sudah incl cost) -> PnL lebih realistis.
    - EXIT juga kena slippage kecil (liquiditas tipis saat SL terkena).
    """
    rsi_o = float(sg.get("rsi_oversold", 35.0))
    rsi_b = float(sg.get("rsi_overbought", 65.0))
    rr = float(sg.get("target_reward_risk_ratio", 2.5))
    min_rr = float(risk.get("min_reward_risk_ratio", 2.0))
    max_bars = int(risk.get("max_hold_bars", 48))
    sl_pct = 0.02
    exit_slip = slippage_pct  # SL kena pasar yg lagi bergerak cepat

    trades = []
    pos = None
    closes = df["close"].tolist()
    rsis = df["rsi14"].tolist()
    for i in range(1, len(closes)):
        price = closes[i]
        rsi = rsis[i]
        if pos:
            pos["bars"] += 1
            exit_reason = None
            if pos["side"] == "buy":
                if price <= pos["sl"]:
                    exit_reason = "SL"
                elif price >= pos["tp"]:
                    exit_reason = "TP"
            else:
                if price >= pos["sl"]:
                    exit_reason = "SL"
                elif price <= pos["tp"]:
                    exit_reason = "TP"
            if exit_reason is None and pos["bars"] >= max_bars:
                exit_reason = "TIMEOUT"
            if exit_reason:
                # exit price kena slippage
                if pos["side"] == "buy":
                    fill = price * (1 - exit_slip)
                    pnl = (fill - pos["entry"]) / pos["entry"]
                else:
                    fill = price * (1 + exit_slip)
                    pnl = (pos["entry"] - fill) / pos["entry"]
                pnl -= 2 * fee_pct
                trades.append({"side": pos["side"], "pnl": pnl,
                               "reason": exit_reason, "bars": pos["bars"]})
                pos = None
        if pos is None:
            if rsi <= rsi_o:
                entry = price * (1 + slippage_pct + spread_pct / 2)
                risk_amt = entry * sl_pct
                tp = entry + risk_amt * rr
                if (tp - entry) / risk_amt >= min_rr:
                    sl = entry - risk_amt
                    pos = {"side": "buy", "entry": entry, "sl": sl, "tp": tp, "bars": 0}
            elif rsi >= rsi_b:
                entry = price * (1 - slippage_pct - spread_pct / 2)
                risk_amt = entry * sl_pct
                tp = entry - risk_amt * rr
                if (entry - tp) / risk_amt >= min_rr:
                    sl = entry + risk_amt
                    pos = {"side": "sell", "entry": entry, "sl": sl, "tp": tp, "bars": 0}
    return trades


# ---------- 2. MONTE CARLO ----------
def _equity_curve(pnls: list, start: float = 1.0) -> np.ndarray:
    eq = [start]
    for p in pnls:
        eq.append(eq[-1] * (1 + p))
    return np.array(eq)


def monte_carlo(trades: list, n_sims: int = 1000, start_equity: float = 10000.0,
                ruin_pct: float = 50.0, seed: int = 42) -> dict:
    """Bootstrap urutan trade -> distribusi outcome.
    Return: distribusi equity akhir, P(ruin), P(profit), CI drawdown,
    ekspektasi, persentil.
    """
    if not trades:
        return {"n_sims": 0, "note": "tidak ada trade utk simulasi"}
    rng = np.random.default_rng(seed)
    pnls = np.array([t["pnl"] for t in trades], dtype=float)
    ruin_level = start_equity * (1 - ruin_pct / 100.0)
    finals = []
    max_dds = []
    ruins = 0
    profits = 0
    for _ in range(n_sims):
        samp = rng.choice(pnls, size=len(pnls), replace=True)  # bootstrap urutan
        eq = _equity_curve(samp.tolist(), start_equity)
        finals.append(eq[-1])
        peak = np.maximum.accumulate(eq)
        dd = (peak - eq) / peak
        max_dds.append(float(dd.max()) * 100.0)
        if eq[-1] <= ruin_level:
            ruins += 1
        if eq[-1] > start_equity:
            profits += 1
    finals = np.array(finals)
    max_dds = np.array(max_dds)
    return {
        "n_sims": n_sims,
        "n_trades": len(trades),
        "equity_final_mean": round(float(finals.mean()), 2),
        "equity_final_median": round(float(np.median(finals)), 2),
        "equity_final_p05": round(float(np.percentile(finals, 5)), 2),
        "equity_final_p95": round(float(np.percentile(finals, 95)), 2),
        "p_ruin": round(ruins / n_sims * 100, 2),     # % sim berakhir di/bawah ruin level
        "p_profit": round(profits / n_sims * 100, 2),  # % sim profit
        "max_dd_mean": round(float(max_dds.mean()), 2),
        "max_dd_p95": round(float(np.percentile(max_dds, 95)), 2),
        "expectancy": round(float(finals.mean() - start_equity), 2),
    }


# ---------- 3. WALK-FORWARD ----------
def walk_forward(df, sg: dict, risk: dict, n_folds: int = 3,
                 fee_pct: float = 0.001, slippage_pct: float = 0.0005,
                 spread_pct: float = 0.0003) -> dict:
    """Split histori jadi n_folds, backtest tiap fold (train=sebelumnya, test=fold ini).
    Return metrik per fold + konsistensi (berapa fold yg profitabel).
    """
    n = len(df)
    if n < n_folds * 100:
        return {"folds": [], "consistent_profit_folds": 0, "note": "data terlalu pendek"}
    fold_size = n // (n_folds + 1)  # sisakan 1 utk warmup train
    folds = []
    profit_folds = 0
    for f in range(n_folds):
        start = (f + 1) * fold_size
        end = start + fold_size
        if end > n:
            break
        sub = df.iloc[start:end].copy()
        tr = simulate_with_costs(sub, sg, risk, fee_pct, slippage_pct, spread_pct)
        m = _metrics(tr)
        if m["net_pct"] > 0:
            profit_folds += 1
        folds.append({"fold": f + 1, "bars": len(sub), **m})
    return {
        "folds": folds,
        "consistent_profit_folds": profit_folds,
        "total_folds": len(folds),
        "robust": profit_folds >= max(1, n_folds - 1),  # >= n-1 fold profit = robust
    }
