"""
NOTIFY/AGENT — PEWE Notification Agent (Telegram)

Fitur utama (instruksi Panji):
  1. Trade Alert   : notifikasi instan saat posisi dibuka (ENTRY) & ditutup (EXIT).
  2. P/L Update    : detail keuntungan/kerugian tiap transaksi yg selesai.
  3. Risk Warning  : jika Risk Manager (NYX/breaker) deteksi volatilitas ekstrem
                     atau drawdown tinggi -> peringatan ke HP.
  4. Daily Report  : ringkasan performa harian (dari Learning Agent) akhir sesi.

Semua lewat notify.telegram.send() (env TELEGRAM_BOT_TOKEN/CHAT_ID).
Fail-safe: kalau telegram disabled / gagal -> print ke log, tdk crash bot.
"""
from __future__ import annotations
import os
from datetime import datetime, date

from notify.telegram import send


def _fmt_usd(x: float) -> str:
    return f"${x:,.2f}"


def trade_alert(kind: str, sym: str, side: str, price: float, qty: float,
                strategy: str = "?", pnl: float = None, settings: dict = None) -> bool:
    """ENTRY atau EXIT alert + P/L detail.
    kind='entry' -> '🟢 OPEN'; kind='exit' -> '🔴 CLOSE' + P/L.
    """
    if settings is None:
        return False
    if kind == "entry":
        emoji = "🟢 OPEN"
        body = (f"{emoji} *{side.upper()} {sym}*\n"
                f"Price: {_fmt_usd(price)}\n"
                f"Size: {qty:.6f}\n"
                f"Strategy: {strategy}")
    else:
        emoji = "🔴 CLOSE"
        if pnl is None:
            pnl = 0.0
        pl_emoji = "✅" if pnl >= 0 else "⚠️"
        body = (f"{emoji} *{side.upper()} {sym}*\n"
                f"Exit Price: {_fmt_usd(price)}\n"
                f"P/L: {pl_emoji} {pnl:+.2f} ({_fmt_usd(pnl)})\n"
                f"Strategy: {strategy}")
    return send(body, settings)


def risk_warning(reason: str, detail: str = "", settings: dict = None) -> bool:
    """Peringatan risiko (volatilitas ekstrem / drawdown tinggi / circuit halt)."""
    if settings is None:
        return False
    body = (f"⚡ *RISK WARNING*\n"
            f"{reason}\n"
            f"{detail}".strip())
    return send(body, settings)


def daily_report(stats: dict, settings: dict = None) -> bool:
    """Ringkasan performa harian (dari Learning Agent / Phoenix).
    stats: {date, equity, realized_pnl, n_trades, win_rate, best, worst,
            open_positions, learning_note}
    """
    if settings is None:
        return False
    eq = stats.get("equity", 0.0)
    rp = stats.get("realized_pnl", 0.0)
    pl = "🟢" if rp >= 0 else "🔴"
    body = (f"📊 *DAILY REPORT* ({stats.get('date', date.today().isoformat())})\n"
            f"Equity: {_fmt_usd(eq)}\n"
            f"Realized P/L: {pl} {rp:+.2f}\n"
            f"Trades: {stats.get('n_trades', 0)} | Win: {stats.get('win_rate', 0):.1f}%\n"
            f"Open Pos: {stats.get('open_positions', 0)}\n"
            f"Best: {stats.get('best', 0):+.2f} | Worst: {stats.get('worst', 0):+.2f}\n"
            f"🧠 {stats.get('learning_note', '')}".strip())
    return send(body, settings)


# ---- helper: track harian biar daily report cuma 1x/hari ----
def maybe_daily_report(state: dict, settings: dict, compute_stats_fn) -> bool:
    """Kirim daily report kalau belum dikirim hari ini.
    state: dict bot (akan di-update last_daily_report_day).
    compute_stats_fn: callable -> dict stats (dari Learning Agent)."""
    today = date.today().isoformat()
    if state.get("last_daily_report_day") == today:
        return False
    try:
        stats = compute_stats_fn()
        stats["date"] = today
        ok = daily_report(stats, settings)
        if ok:
            state["last_daily_report_day"] = today
        return ok
    except Exception as e:
        print(f"[NOTIFY] daily_report gagal: {e}")
        return False
