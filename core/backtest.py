"""
BACKTEST — ukur profitabilitas strategi (PEWE)
Ambil OHLCV historis via ccxt, simulasikan sinyal RSI (sama persis dg Kodok)
+ manajemen EXIT (TP/SL/R:R) per token, hitung metrik.

Metrik: total trades, win-rate, profit factor, net PnL %, max drawdown,
avg hold (bar), expectancy.

Strategi (mirror Kodok.generate_signal + risk_engine):
  - BUY bila RSI <= oversold (entry=close, SL=2%, TP=R:R*risk)
  - SELL bila RSI >= overbought (mirror)
  - Tutup bila TP/SL kena atau max_hold_bars
Jalan per-bar (walk-forward sederhana), 1 posisi per token yg aktif.
"""
from __future__ import annotations
import math
from core.indicators import add_indicators


def _simulate_one(df, sg: dict, risk: dict, fee_pct: float = 0.001):
    """Simulasikan 1 token. Return list trade dict."""
    rsi_o = float(sg.get("rsi_oversold", 35.0))
    rsi_b = float(sg.get("rsi_overbought", 65.0))
    rr = float(sg.get("target_reward_risk_ratio", 2.5))
    min_rr = float(risk.get("min_reward_risk_ratio", 2.0))
    max_bars = int(risk.get("max_hold_bars", 48))
    sl_pct = 0.02  # 2% stop (sama dg backtest sebelumnya)

    trades = []
    pos = None  # {side, entry, sl, tp, bars}
    closes = df["close"].tolist()
    rsis = df["rsi14"].tolist()
    for i in range(1, len(closes)):
        price = closes[i]
        rsi = rsis[i]
        # proses exit dulu
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
                if pos["side"] == "buy":
                    pnl = (price - pos["entry"]) / pos["entry"]
                else:
                    pnl = (pos["entry"] - price) / pos["entry"]
                pnl -= 2 * fee_pct  # fee masuk + keluar
                trades.append({"side": pos["side"], "pnl": pnl, "reason": exit_reason, "bars": pos["bars"]})
                pos = None
        # entry bila tidak ada posisi
        if pos is None:
            if rsi <= rsi_o:
                risk_amt = price * sl_pct
                tp = price + risk_amt * rr
                if (tp - price) / risk_amt >= min_rr:
                    pos = {"side": "buy", "entry": price, "sl": price - risk_amt, "tp": tp, "bars": 0}
            elif rsi >= rsi_b:
                risk_amt = price * sl_pct
                tp = price - risk_amt * rr
                if (price - tp) / risk_amt >= min_rr:
                    pos = {"side": "sell", "entry": price, "sl": price + risk_amt, "tp": tp, "bars": 0}
    return trades


def _metrics(trades: list) -> dict:
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "net_pct": 0.0,
                "max_dd": 0.0, "avg_bars": 0.0, "expectancy": 0.0}
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = len(wins) / len(trades)
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    net = sum(t["pnl"] for t in trades)
    # equity curve drawdown
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for t in trades:
        eq *= (1 + t["pnl"])
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)
    avg_bars = sum(t["bars"] for t in trades) / len(trades)
    expectancy = net / len(trades)
    return {
        "trades": len(trades), "win_rate": round(win_rate * 100, 2),
        "profit_factor": round(pf, 2) if pf != float("inf") else 999.0,
        "net_pct": round(net * 100, 2), "max_dd": round(max_dd * 100, 2),
        "avg_bars": round(avg_bars, 1), "expectancy": round(expectancy * 100, 4),
    }


def run(market, settings: dict, symbols: list, limit: int = 500, testnet: bool = False, save: bool = True,
        mc: bool = True, wf: bool = True,
        fee_pct: float = 0.001, slippage_pct: float = 0.0005, spread_pct: float = 0.0003) -> dict:
    """Backtest beberapa token. Return dict per-symbol + aggregate + MONTE CARLO.
    mc=True -> jalankan Monte Carlo + walk-forward (evaluasi statistik nyata).
    """
    from core.montecarlo import simulate_with_costs, monte_carlo, walk_forward
    sg = settings.get("signal", {})
    rk = settings.get("risk", {})
    out = {}
    all_trades = []
    for sym in symbols:
        try:
            df = add_indicators(market.ohlcv(sym, settings.get("exchange", {}).get("timeframe", "1h"), limit))
            if df is None or df.empty or "rsi14" not in df.columns:
                continue
            # simulator DENGAN slippage + spread (realistis)
            tr = simulate_with_costs(df, sg, rk, fee_pct, slippage_pct, spread_pct)
            m = _metrics(tr)
            # Monte Carlo per token (jika mc aktif & cukup trade)
            if mc and len(tr) >= 10:
                m["monte_carlo"] = monte_carlo(tr, n_sims=500)
            if wf and len(df) >= 600:
                m["walk_forward"] = walk_forward(df, sg, rk, n_folds=3,
                                                 fee_pct=fee_pct, slippage_pct=slippage_pct,
                                                 spread_pct=spread_pct)
            out[sym] = m
            all_trades.extend(tr)
        except Exception as e:
            out[sym] = {"error": str(e)}
    out["__AGGREGATE__"] = _metrics(all_trades)
    if mc and len(all_trades) >= 10:
        out["__AGGREGATE__"]["monte_carlo"] = monte_carlo(all_trades, n_sims=1000)
    if save:
        import os, json
        os.makedirs("logs", exist_ok=True)
        with open("logs/backtest_report.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    return out
    sg = settings.get("signal", {})
    rk = settings.get("risk", {})
    out = {}
    all_trades = []
    for sym in symbols:
        try:
            if testnet:
                df = add_indicators(market.ohlcv(sym, settings.get("exchange", {}).get("timeframe", "1h"), limit))
            else:
                df = add_indicators(market.ohlcv(sym, settings.get("exchange", {}).get("timeframe", "1h"), limit))
            if df is None or df.empty or "rsi14" not in df.columns:
                continue
            tr = _simulate_one(df, sg, rk)
            m = _metrics(tr)
            out[sym] = m
            all_trades.extend(tr)
        except Exception as e:
            out[sym] = {"error": str(e)}
    out["__AGGREGATE__"] = _metrics(all_trades)
    if save:
        import os, json
        os.makedirs("logs", exist_ok=True)
        with open("logs/backtest_report.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    return out
