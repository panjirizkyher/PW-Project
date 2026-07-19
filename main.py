"""
MAIN — entry point Trading Desk autonomous.
Usage:
  python main.py                 # loop sesuai schedule (run_every_minutes)
  python main.py --once          # jalan satu kali (buat test)
  python main.py backtest        # ukur profitabilitas strategi di data historis
  python main.py backtest --mock # backtest offline (data tiruan)
"""
from __future__ import annotations
import sys
import time
import yaml

from core.env_loader import load_env
from core.orchestrator import Orchestrator
from data.market import MarketData


def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_backtest(settings: dict, mock: bool, limit: int = 500):
    from core.backtest import run
    print(f"[BACKTEST] mengambil data historis … (limit={limit} candle ≈ {limit/24:.0f} hari)")
    if mock:
        from data.mock import mock_ohlcv
        from core.indicators import add_indicators
        syms = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
        # mock market stub
        class _M:
            def ohlcv(self, sym, tf, limit):
                return add_indicators(mock_ohlcv(limit, seed=hash(sym) % 1000))
        res = run(_M(), settings, syms, limit=limit, testnet=False)
    else:
        mode = settings.get("mode", "demo")
        m = MarketData(settings.get("exchange", {}).get("id", "binance"), testnet=(mode == "demo"))
        # ambil daftar token likuid dari screener
        from core.screener import list_symbols
        syms = list_symbols(m)[:20] or ["BTC/USDT"]
        res = run(m, settings, syms, limit=limit, testnet=(mode == "demo"))
    print("\n=== BACKTEST RESULTS ===")
    for sym, m in res.items():
        if sym == "__AGGREGATE__":
            continue
        if "error" in m:
            print(f"  {sym}: ERROR {m['error']}")
            continue
        print(f"  {sym:12s} trades={m['trades']:3d} win={m['win_rate']:5.1f}% "
              f"PF={m['profit_factor']:6.2f} net={m['net_pct']:7.2f}% DD={m['max_dd']:5.2f}% "
              f"avgBars={m['avg_bars']:4.1f} exp={m['expectancy']:6.4f}%")
    a = res["__AGGREGATE__"]
    print(f"\n  >>> AGGREGATE: trades={a['trades']} win={a['win_rate']}% "
          f"PF={a['profit_factor']} net={a['net_pct']}% maxDD={a['max_dd']}% exp={a['expectancy']}%")
    verdict = "PROFITABLE ✅" if a["profit_factor"] > 1.2 and a["net_pct"] > 0 else "BELUM PROFIT ⚠️"
    print(f"  >>> VERDICT: {verdict}")


def main():
    load_env()
    settings = load_settings()

    if "backtest" in sys.argv:
        mock = "--mock" in sys.argv
        # periode: --months 6 -> 4320 candle 1h (~6 bulan); --limit N override
        tf = settings.get("exchange", {}).get("timeframe", "1h")
        months = None
        limit = None
        for i, a in enumerate(sys.argv):
            if a == "--months" and i + 1 < len(sys.argv):
                months = float(sys.argv[i + 1])
            if a == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
        if limit is None:
            limit = int(4320 * months) if months else 500  # default 21 hari
        run_backtest(settings, mock, limit=limit)
        return

    mock = "--mock" in sys.argv
    orch = Orchestrator(settings, mock=mock)

    if "--once" in sys.argv:
        print(orch.run())
        return

    interval = int(settings.get("schedule", {}).get("run_every_minutes", 60)) * 60
    print(f"[TRADING DESK] autonomous loop — tiap {interval}s. Ctrl+C untuk berhenti.")
    try:
        while True:
            try:
                print(orch.run())
            except Exception as e:
                print(f"[LOOP] error: {e}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[TRADING DESK] dihentikan oleh user.")


if __name__ == "__main__":
    main()
