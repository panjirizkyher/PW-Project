"""
AGENT 4 — NAKAMOTO X (Crypto Specialist)
Sentimen crypto dari Fear & Greed + catatan on-chain (placeholder).
"""
from __future__ import annotations


class Nakamoto:
    def __init__(self, llm):
        self.llm = llm
        self.name = "NAKAMOTO X"

    def analyze(self, fg: dict) -> str:
        if not fg:
            return "(bukan aset crypto — lewati)"
        val = fg.get("value", "n/a")
        cls = fg.get("classification", "n/a")
        text = (
            f"Fear & Greed: {val} ({cls}). "
            + ("Greed tinggi — hati-hati top, jangan FOMO. " if isinstance(val, int) and val > 70
               else "Fear tinggi — akumulasi pelan, DYOR. " if isinstance(val, int) and val < 30
               else "Sentimen netral, tunggu konfirmasi. ")
            + "HODL responsibly, wen moon tapi pake stop loss 😏"
        )
        return text
