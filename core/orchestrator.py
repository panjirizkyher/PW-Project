"""
ORCHESTRATOR — PEWE
Menjalankan alur kerja tim: data -> Marcus -> Rafael -> Nakamoto -> Kodok(sinyal)
-> Eleanor(risk HARD gate) -> Grace(psikologi) -> executor(paper) -> notify.
"""
from __future__ import annotations
from datetime import datetime
from core.llm_client import LLMClient
from core.indicators import add_indicators
from core.risk_engine import RiskEngine, ProposedTrade
from core.circuit_breaker import CircuitBreaker
from core.executor import PaperExecutor
from data.market import MarketData
from data.onchain import fear_greed
from data.macro import next_events
from agents.marcus import Marcus
from agents.rafael import Rafael
from agents.nakamoto import Nakamoto
from agents.eleanor import Eleanor
from agents.grace import Grace
from agents.kodok import Kodok
from notify.telegram import send


class Orchestrator:
    def __init__(self, settings: dict, mock: bool = False):
        self.s = settings
        self.mock = mock
        self.llm = LLMClient(settings)
        self.market = MarketData(settings.get("exchange", {}).get("id", "binance"))
        self.risk = RiskEngine(settings)
        self.breaker = CircuitBreaker()
        self.exec = PaperExecutor(self.risk.balance)
        self.marcus = Marcus(self.llm)
        self.rafael = Rafael()
        self.naka = Nakamoto(self.llm)
        self.eleanor = Eleanor()
        self.grace = Grace(self.llm)
        self.kodok = Kodok(settings)
        self.is_crypto = "USD" in settings.get("exchange", {}).get("symbol", "") or \
                         "USDT" in settings.get("exchange", {}).get("symbol", "")

    def run(self) -> str:
        ex = self.s.get("exchange", {})
        symbol, tf = ex.get("symbol", "BTC/USDT"), ex.get("timeframe", "1h")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        if self.breaker.halted:
            msg = f"⛔ Bot HALT (circuit breaker): {self.breaker.halt_reason}\nTidak ada aksi sampai di-resume manual."
            send(msg, self.s)
            return msg

        # 1. DATA
        if self.mock:
            from data.mock import mock_ohlcv
            df = add_indicators(mock_ohlcv(200))
            last = float(df.iloc[-1]["close"])
            fg = {"value": 54, "classification": "Neutral"} if self.is_crypto else {}
        else:
            df = add_indicators(self.market.ohlcv(symbol, tf, 200))
            last = self.market.last_price(symbol)
            fg = fear_greed() if self.is_crypto else {}
        macro = next_events()

        # 2. MARCUS (makro)
        marcus_txt = self.marcus.analyze(macro, fg)

        # 3. RAFAEL (teknikal)
        raf = self.rafael.analyze(df)
        bias = raf.get("bias", "n/a")

        # 4. NAKAMOTO (crypto)
        naka_txt = self.naka.analyze(fg) if self.is_crypto else "(bukan aset crypto — lewati)"

        # 5. KODOK (sinyal deterministik)
        sig = self.kodok.generate_signal(df, last) if (last and not df.empty) else {}
        trade_ok, rr_msg = False, ""
        fill_info = ""
        if sig and sig.get("side") in ("buy", "sell"):
            t = ProposedTrade(symbol, sig["side"], sig["entry"],
                              sig["stop_loss"], sig["take_profit"], sig["conviction"])
            # ELEANOR — HARD RISK GATE
            trade_ok, rr_msg = self.risk.validate(t)
            can_open, open_msg = self.risk.can_open_new(len(self.exec.positions))
            eleanor_txt = self.eleanor.comment(trade_ok and can_open, rr_msg,
                                              len(self.exec.positions), self.risk.max_open)
            if trade_ok and can_open:
                qty = self.risk.position_size(t)
                fill = self.exec.execute(symbol, sig["side"], qty, sig["entry"])
                fill_info = f"PAPER FILL: {sig['side']} {qty:.6f} @ {sig['entry']:.2f}"
                # circuit breaker check
                breached = self.risk.daily_loss_breached(self.exec.balance - self.risk.balance)
                self.breaker.check(breached)
            else:
                fill_info = f"(tidak dieksekusi) {open_msg or rr_msg}"
        else:
            eleanor_txt = self.eleanor.comment(True, "Hold — tidak ada sinyal.", 0, self.risk.max_open)
            fill_info = "Sinyal: HOLD (RSI netral)."

        # 6. GRACE (psikologi)
        grace_txt = self.grace.reflect("FOMO" if sig.get("conviction", 0) > 0.8 else "fear/overtrading")

        # 7. RENDER BRIEFING
        briefing = (
            f"┌─ 📋 TRADING DESK BRIEFING — {now} ─┐\n"
            f"│ ASSET: {symbol} | TF: {tf} | BIAS: {bias} | MODE: {self.s.get('mode')}\n\n"
            f"🔷 PROF. MARCUS (Makro)\n   → {marcus_txt}\n\n"
            f"🔷 RAFAEL (Teknikal)\n   → {raf.get('text')}\n\n"
            f"🔷 NAKAMOTO X (Crypto)\n   → {naka_txt}\n\n"
            f"🔷 KODOK (Sinyal)\n   → {sig or 'HOLD'}\n\n"
            f"🔷 MADAME ELEANOR (Risk)\n   → {eleanor_txt}\n   → {fill_info}\n\n"
            f"🔷 DR. GRACE (Psikologi)\n   → {grace_txt}\n\n"
            f"└─ ⚠️ DISCLAIMER: Bukan nasihat keuangan. ─┘"
        )
        send(briefing, self.s)
        # audit log
        self._audit(briefing)
        return briefing

    def _audit(self, text: str):
        import os
        os.makedirs("logs", exist_ok=True)
        with open("logs/audit.log", "a", encoding="utf-8") as f:
            f.write(text + "\n" + "=" * 40 + "\n")
