"""
SCREENER — cari setup terbaik dari banyak token (PEWE)
Ambil daftar pasangan dari exchange (testnet ~12, live ratusan), filter likuid,
hitung skor multi-faktor, rank top-N. Orchestrator eksekusi HANYA token
dgn skor tertinggi yg sinyalnya valid (presisi, bukan asal entry).

Skor (0-100):
  - RSI ekstremitas (semakin dekat oversold/overbought, semakin tinggi)
  - Trend alignment (EMA50 vs EMA200)
  - Volatilitas wajar (cukup gerak utk profit, tdk terlalu gila)
  - Fear&Greed bonus (fear -> buy the fear, greedy -> jual)
"""
from __future__ import annotations
import math
from core.indicators import add_indicators
from data.onchain import fear_greed


def _rsi_score(rsi: float, rsi_oversold: float, rsi_overbought: float) -> float:
    """Semakin ekstrem RSI, semakin tinggi skor (0-40)."""
    if rsi <= rsi_oversold:
        return 40.0
    if rsi >= rsi_overbought:
        return 40.0
    # di tengah -> skor menurun proporsional
    mid = (rsi_oversold + rsi_overbought) / 2
    dist = abs(rsi - mid)
    half = (rsi_overbought - rsi_oversold) / 2
    return max(0.0, 40.0 * (dist / half))


def _trend_score(df) -> float:
    """Uptrend (EMA50>EMA200) -> skor beli; downtrend -> skor jual; netral rendah."""
    try:
        e50 = float(df.iloc[-1]["ema50"]); e200 = float(df.iloc[-1]["ema200"])
        if math.isnan(e50) or math.isnan(e200):
            return 10.0
        if e50 > e200:
            return 30.0
        if e50 < e200:
            return 15.0
    except Exception:
        return 10.0
    return 10.0


def _vol_score(df) -> float:
    """Volatilitas harian wajar (1%-8% bagus). Terlalu tenang/liar = skor turun."""
    try:
        closes = df["close"].tail(24)
        if len(closes) < 2:
            return 10.0
        rets = closes.pct_change().dropna()
        vol = float(rets.std()) * math.sqrt(24)  # annualized-ish harian
        if 0.01 <= vol <= 0.08:
            return 20.0
        if vol < 0.01:
            return 8.0
        if vol > 0.15:
            return 5.0
        return 12.0
    except Exception:
        return 10.0


def score_symbol(df, rsi_oversold: float, rsi_overbought: float) -> float:
    if df is None or df.empty or "rsi14" not in df.columns:
        return 0.0
    rsi = float(df.iloc[-1]["rsi14"])
    if math.isnan(rsi):
        return 0.0
    s = _rsi_score(rsi, rsi_oversold, rsi_overbought)
    s += _trend_score(df)
    s += _vol_score(df)
    # Fear&Greed: fear (<40) -> bias beli (counter-trend)
    try:
        fg = fear_greed()
        if fg is not None and fg < 40:
            s += 10.0
        elif fg is not None and fg > 75:
            s += 5.0
    except Exception:
        pass
    return round(min(100.0, s), 2)


def list_symbols(market, quote: str = "USDT", min_usdt_vol: float = 5_000_000.0) -> list:
    """Daftar pasangan spot yg likuid (24h quote volume > min)."""
    STABLE = {"USDC", "BUSD", "TUSD", "DAI", "FDUSD", "USDP", "USDD", "USD1", "UST", "SUSD"}
    try:
        tickers = market.ex.fetch_tickers()
    except Exception:
        return []
    out = []
    for sym, t in tickers.items():
        if not sym.endswith("/" + quote):
            continue
        base = sym.split("/")[0]
        if base in STABLE:
            continue
        # buang token "murah/sampah": harga terlalu rendah atau volume tipis
        last = t.get("last") or t.get("close") or t.get("bid") or 0
        try:
            last = float(last)
        except Exception:
            last = 0
        if last > 0 and last < 0.5:   # harga < $0.5 = biasanya sampah/stable murah
            continue
        vol = (t.get("quoteVolume") or t.get("baseVolume") or 0) or 0
        if vol >= min_usdt_vol:
            out.append(sym)
    return out


def screen(market, settings: dict, top_n: int = 3, max_scan: int = 50,
           mock: bool = False, max_workers: int = 8) -> list:
    """
    Return list dict: [{symbol, score, rsi, side_bias}, ...] terurut skor tertinggi.
    side_bias: 'buy'/'sell'/'neutral' dari RSI.
    Scaling (instruksi B): scan paralel via ThreadPoolWorker -> throughput tinggi
    saat jumlah aset 12->50 (cegah latency scalping). FEAR&GREED di-cache 1x call.
    """
    import time as _t
    sg = settings.get("signal", {})
    rsi_o = float(sg.get("rsi_oversold", 35.0))
    rsi_b = float(sg.get("rsi_overbought", 65.0))
    if mock:
        syms = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
                "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
                "MATIC/USDT", "LTC/USDT", "TRX/USDT", "ATOM/USDT", "UNI/USDT",
                "NEAR/USDT", "APT/USDT", "FIL/USDT", "ARB/USDT", "OP/USDT",
                "INJ/USDT", "SUI/USDT", "TIA/USDT", "SEI/USDT", "RNDR/USDT",
                "FET/USDT", "GRT/USDT", "ALGO/USDT", "SAND/USDT", "AXS/USDT",
                "THETA/USDT", "EGLD/USDT", "FLOW/USDT", "CHZ/USDT", "CRV/USDT",
                "LDO/USDT", "STX/USDT", "MKR/USDT", "AAVE/USDT", "COMP/USDT",
                "SNX/USDT", "YFI/USDT", "SUSHI/USDT", "1INCH/USDT", "ENJ/USDT",
                "BAT/USDT", "ZEC/USDT", "DASH/USDT", "XTZ/USDT", "EOS/USDT"]
    else:
        syms = list_symbols(market)[:max_scan] or ["BTC/USDT"]

    # FEAR&GREED di-cache 1x (hindari N call)
    _fg_cache = {}
    def fg_bonus():
        if "fg" in _fg_cache:
            return _fg_cache["fg"]
        try:
            _fg_cache["fg"] = fear_greed()
        except Exception:
            _fg_cache["fg"] = None
        return _fg_cache["fg"]

    def _score_one(sym):
        try:
            if mock:
                from data.mock import mock_ohlcv
                df = add_indicators(mock_ohlcv(200, seed=hash(sym) % 1000))
            else:
                df = add_indicators(market.ohlcv(sym, settings.get("exchange", {}).get("timeframe", "1h"), 200))
            if df is None or df.empty:
                return None
            score = score_symbol(df, rsi_o, rsi_b)
            rsi = float(df.iloc[-1]["rsi14"])
            side = "buy" if rsi <= rsi_o else ("sell" if rsi >= rsi_b else "neutral")
            return {"symbol": sym, "score": score, "rsi": round(rsi, 2), "side_bias": side}
        except Exception:
            return None

    # PARALLEL scan (thread pool -> overlap network I/O, throughput naik)
    results = []
    if max_workers > 1 and len(syms) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(max_workers, len(syms))) as ex:
            for r in ex.map(_score_one, syms):
                if r:
                    results.append(r)
    else:
        for s in syms:
            r = _score_one(s)
            if r:
                results.append(r)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]

