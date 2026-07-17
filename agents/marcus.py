"""
AGENT 1 — PROF. MARCUS (Chief Analyst / Makro)
LLM persona untuk konteks makro. Data makro dari data.macro, sentiment dari
fear&greed (crypto) + asumsi risk-on/off.
"""
from __future__ import annotations


class Marcus:
    def __init__(self, llm):
        self.llm = llm
        self.name = "PROF. MARCUS"

    def analyze(self, macro_events: list, fg: dict) -> str:
        sys = (
            "You are Prof. Marcus, PhD in Financial Economics, 20+ yrs Wall Street. "
            "Formal, data-driven, cite central bank policy. Respond in Indonesian, "
            "concise (max 4 bullets)."
        )
        fg_txt = fg.get("classification", "n/a") if fg else "n/a"
        usr = (
            f"Katalis minggu ini: {macro_events}. "
            f"Crypto Fear&Greed: {fg_txt}. "
            "Berikan sentimen makro (risk-on/risk-off) & korelasi aset utama."
        )
        return self.llm.ask(sys, usr)
