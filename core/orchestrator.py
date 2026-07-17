"""
ORCHESTRATOR — PEWE
Menjalankan alur kerja tim: data -> Marcus -> Rafael -> Nakamoto -> Kodok(sinyal)
-> Eleanor(risk HARD gate) -> Grace(psikologi) -> executor(paper) -> notify.
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from core.llm_client import LLMClient
from core.indicators import add_indicators
from core.risk_engine import RiskEngine, ProposedTrade
from core.circuit_breaker import CircuitBreaker
from core.executor import PaperExecutor, ExchangeExecutor
from core.state import load_state, save_state, reset_day_if_new
from data.onchain import fear_greed
from data.macro import next_events
from data.market import MarketData
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
        self.mode = settings.get("mode", "paper")
        self.llm = LLMClient(settings)
        self.market = MarketData(
            settings.get("exchange", {}).get("id", "binance"),
            testnet=(self.mode == "demo"),
        )
        self.risk = RiskEngine(settings)
        self.breaker = CircuitBreaker()
        # executor dipilih berdasar mode
        self.exec = self._build_executor()
        # state posisi persisten (paper balance dari settings)
        self.state = load_state()
        self.state = reset_day_if_new(self.state)
        if self.state.get("equity") is None:
            self.state["equity"] = self.risk.balance
        self.marcus = Marcus(self.llm)
        self.rafael = Rafael()
        self.naka = Nakamoto(self.llm)
        self.eleanor = Eleanor()
        self.grace = Grace(self.llm)
        self.kodok = Kodok(settings)
        self.is_crypto = "USD" in settings.get("exchange", {}).get("symbol", "") or \
                         "USDT" in settings.get("exchange", {}).get("symbol", "")

    def _build_executor(self):
        mode = self.mode
        if mode in ("paper", "backtest"):
            return PaperExecutor()
        # demo (testnet) atau live -> butuh API key dari env
        key_map = self.s.get("api_keys", {}).get(mode, {})
        ak = os.environ.get(key_map.get("key_env", ""), "")
        sk = os.environ.get(key_map.get("secret_env", ""), "")
        testnet = (mode == "demo")
        if not ak or not sk:
            # tanpa key, fallback paper agar tidak crash
            return PaperExecutor()
        return ExchangeExecutor(self.s["exchange"]["id"], ak, sk, testnet=testnet)

    def run(self) -> str:
        out = self.run_structured()
        # audit log
        self._audit(out["briefing_text"])
        return out["briefing_text"]

    def run_structured(self) -> dict:
        """Sama seperti run(), tapi kembalikan dict terstruktur + tulis briefing.json."""
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
        eleanor_txt = ""
        fill_info = ""
        trade_action = "hold"

        # === MANAJEMEN EXIT dulu (tutup posisi bila TP/SL/time kena) ===
        exited_this_cycle = False
        for pos in list(self.state["positions"]):
            exit_side = "sell" if pos["side"] == "buy" else "buy"
            reason = None
            if pos["side"] == "buy":
                if last <= pos["stop_loss"]:
                    reason = "SL"
                elif last >= pos["take_profit"]:
                    reason = "TP"
            else:
                if last >= pos["stop_loss"]:
                    reason = "SL"
                elif last <= pos["take_profit"]:
                    reason = "TP"
            # timeout: tutup bila lewat max_bars tanpa menyentuh SL/TP
            max_bars = int(self.s.get("risk", {}).get("max_hold_bars", 48))
            if reason is None and (pos.get("bars", 0) + 1) >= max_bars:
                reason = "TIMEOUT"
            if reason:
                fill = self.exec.close(symbol, exit_side, pos["qty"], last)
                pnl = (fill.price - pos["entry"]) * pos["qty"] if pos["side"] == "buy" else (pos["entry"] - fill.price) * pos["qty"]
                self.state["equity"] += pnl
                self.state["realized_pnl"] += pnl
                self.state["positions"].remove(pos)
                fill_info = f"EXIT {reason}: {exit_side} {pos['qty']:.6f} @ {fill.price:.2f} | PnL {pnl:+.2f}"
                trade_action = f"exit_{reason.lower()}"
                exited_this_cycle = True
                # circuit breaker: cek drawdown harian
                self.breaker.check(self.risk.daily_loss_breached(self.state["realized_pnl"]))

        # === ENTRY (buka posisi bila sinyal + gate lolos + masih bisa) ===
        if not exited_this_cycle and sig and sig.get("side") in ("buy", "sell"):
            t = ProposedTrade(symbol, sig["side"], sig["entry"],
                              sig["stop_loss"], sig["take_profit"], sig["conviction"])
            trade_ok, rr_msg = self.risk.validate(t)
            can_open, open_msg = self.risk.can_open_new(len(self.state["positions"]))
            eleanor_txt = self.eleanor.comment(trade_ok and can_open, rr_msg,
                                              len(self.state["positions"]), self.risk.max_open)
            if trade_ok and can_open and not self.state["positions"]:
                # baru buka 1 posisi sekaligus (anti over-leverage)
                qty = self.risk.position_size(t)
                fill = self.exec.execute(symbol, sig["side"], qty, sig["entry"])
                self.state["positions"].append({
                    "symbol": symbol, "side": sig["side"], "qty": qty,
                    "entry": fill.price, "stop_loss": sig["stop_loss"],
                    "take_profit": sig["take_profit"], "bars": 0,
                })
                fill_info = f"{'PAPER' if fill.paper else 'LIVE'} FILL: {sig['side']} {qty:.6f} @ {fill.price:.2f}"
                trade_action = "entry"
            elif not eleanor_txt:
                eleanor_txt = self.eleanor.comment(trade_ok and can_open, rr_msg,
                                                  len(self.state["positions"]), self.risk.max_open)
        else:
            if not eleanor_txt:
                eleanor_txt = self.eleanor.comment(True, "Hold — tidak ada sinyal.", 0, self.risk.max_open)
            if not fill_info:
                fill_info = "Sinyal: HOLD (RSI netral)."

        # simpan state (posisi + equity persist antar siklus)
        save_state(self.state)

        # 6. GRACE (psikologi)
        grace_txt = self.grace.reflect("FOMO" if sig.get("conviction", 0) > 0.8 else "fear/overtrading")

        # 7. RENDER BRIEFING (terstruktur + teks)
        sections = [
            {"key": "marcus",   "name": "PROF. MARCUS",     "role": "Makro",       "text": marcus_txt},
            {"key": "rafael",   "name": "RAFAEL",           "role": "Teknikal",    "text": raf.get("text", "")},
            {"key": "naka",     "name": "NAKAMOTO X",       "role": "Crypto",      "text": naka_txt},
            {"key": "kodok",    "name": "KODOK",            "role": "Sinyal",      "text": str(sig) if sig else "HOLD"},
            {"key": "eleanor",  "name": "MADAME ELEANOR",   "role": "Risk",        "text": f"{eleanor_txt}\n{fill_info}"},
            {"key": "grace",    "name": "DR. GRACE",        "role": "Psikologi",   "text": grace_txt},
        ]
        briefing_text = (
            f"┌─ 📋 TRADING DESK BRIEFING — {now} ─┐\n"
            f"│ ASSET: {symbol} | TF: {tf} | BIAS: {bias} | MODE: {self.s.get('mode')}\n\n"
            + "\n\n".join(f"🔷 {s['name']} ({s['role']})\n   → {s['text']}" for s in sections)
            + f"\n\n└─ ⚠️ DISCLAIMER: Bukan nasihat keuangan. ─┘"
        )
        out = {
            "timestamp": now,
            "asset": symbol,
            "timeframe": tf,
            "bias": bias,
            "mode": self.s.get("mode"),
            "signal": sig or {"side": "hold"},
            "action": trade_action,
            "equity": round(self.state.get("equity", 0), 2),
            "realized_pnl": round(self.state.get("realized_pnl", 0), 2),
            "open_positions": len(self.state.get("positions", [])),
            "halted": self.breaker.halted,
            "sections": sections,
            "briefing_text": briefing_text,
        }
        self._write_json(out)
        send(briefing_text, self.s)
        return out

    def _write_json(self, out: dict):
        import os
        os.makedirs("logs", exist_ok=True)
        with open("logs/briefing.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

    def _audit(self, text: str):
        import os
        os.makedirs("logs", exist_ok=True)
        with open("logs/audit.log", "a", encoding="utf-8") as f:
            f.write(text + "\n" + "=" * 40 + "\n")
