"""
AGENT 5 — DR. GRACE (Trading Psychologist)
Refleksi bias kognitif. Ringan, empati, bahasa Indonesia.
"""
from __future__ import annotations


class Grace:
    def __init__(self, llm):
        self.llm = llm
        self.name = "DR. GRACE"

    def reflect(self, bias_hint: str = "") -> str:
        sys = (
            "You are Dr. Grace, behavioral psychologist for traders. Empathetic, calm, "
            "ask reflective questions. Indonesian, max 3 sentences."
        )
        usr = f"Trader mungkin mengalami: {bias_hint or 'FOMO / fear / overtrading'}. Beri satu saran mindfulness."
        return self.llm.ask(sys, usr)
