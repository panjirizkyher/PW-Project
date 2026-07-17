"""
MACRO — economic calendar / news placeholder.
LEVEL C autonomous: idealnya ambil dari API kalender ekonomi (mis. TradingEconomics,
ForexFactory RSS, atau FMP). Di sini kita sediakan hook + fallback statis agar
Prof. Marcus punya konteks walau tanpa API key.
"""
from __future__ import annotations
from datetime import datetime


def next_events(week_of: datetime | None = None) -> list[dict]:
    """
    TODO: ganti dengan fetch API nyata (FOMC/NFP/CPI).
    Return list of {date, event, impact}.
    Fallback: statis agar pipeline tidak kosong.
    """
    return [
        {"date": "placeholder", "event": "FOMC / NFP / CPI (isi via API makro)", "impact": "high"},
    ]
