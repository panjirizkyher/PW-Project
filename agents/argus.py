"""
AGENT — ARGUS (Market Surveillance)
Pemantau pasar: scan anomali, likuiditas menipis, spike volatilitas,
serta daftar watchlist (screener). Deterministik (no LLM).
Output: alert + daftar simbol mencurigakan yg harus dihindari/dinasari.
"""
from __future__ import annotations
import pandas as pd


class Argus:
    def __init__(self):
        self.name = "ARGUS"

    def scan(self, df: pd.DataFrame, symbol: str = "") -> dict:
        """Deteksi anomali pada 1 token. Return dict alert."""
        if df is None or df.empty or "close" not in df.columns:
            return {"symbol": symbol, "alert": "n/a", "suspicious": False}
        try:
            closes = df["close"].astype(float)
            rets = closes.pct_change().dropna().tail(20)
            vol = float(rets.std() or 0.0)
            last_ret = float(rets.iloc[-1]) if len(rets) else 0.0
            # spike: return terakhir > 3x volatilitas normal
            spike = abs(last_ret) > 3 * vol if vol > 0 else False
            # likuiditas: bandingkan volume terakhir vs rata-rata
            liq = "n/a"
            suspicious = False
            if "volume" in df.columns:
                v = df["volume"].astype(float)
                avg_v = float(v.tail(20).mean())
                last_v = float(v.iloc[-1])
                liq = "tipis" if (avg_v > 0 and last_v < 0.3 * avg_v) else "wajar"
                if liq == "tipis":
                    suspicious = True
            if spike:
                suspicious = True
            alert = []
            if spike:
                alert.append(f"spike {last_ret*100:+.1f}% (vol {vol*100:.1f}%)")
            if liq == "tipis":
                alert.append("likuiditas tipis")
            return {"symbol": symbol, "alert": "; ".join(alert) or "normal",
                    "suspicious": suspicious, "vol": round(vol, 4)}
        except Exception:
            return {"symbol": symbol, "alert": "error", "suspicious": False}

    def watchlist(self, top: list) -> str:
        """Ringkas screener top-N jadi watchlist teks."""
        if not top:
            return "(watchlist kosong)"
        lines = [f"Argus watchlist ({len(top)}):"]
        for r in top:
            lines.append(f"  {r['symbol']}: skor {r.get('score')} | RSI {r.get('rsi')} | {r.get('side_bias')}")
        return "\n".join(lines)
