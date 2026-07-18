"""
ORCHESTRATOR — PEWE
Menjalankan alur kerja tim 8 agent:
  data -> Chronos(makro/timing) -> Helios(trend) -> Vega(quant) -> Leviathan(sinyal/eksekusi)
  -> Nyx(risk HARD gate) -> Atlas(head strategist) -> Argus(surveillance) -> Phoenix(recovery)
  -> executor(paper/testnet) -> notify.
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
from core.screener import screen
from core.market_snapshot import snapshot as market_snapshot
from core.account import snapshot as account_snapshot
from core.consensus import decide as decide_consensus, summarize as consensus_summarize
from data.onchain import fear_greed
from data.macro import next_events
from data.sentiment import market_psychology, coingecko_global, coingecko_trending
from data.market import MarketData
from agents.chronos import Chronos
from agents.helios import Helios
from agents.vega import Vega
from agents.nyx import Nyx
from agents.atlas import Atlas
from agents.argus import Argus
from agents.phoenix import Phoenix
from agents.leviathan import Leviathan
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
        self.chronos = Chronos(self.llm)
        self.helios = Helios()
        self.vega = Vega(self.llm)
        self.nyx = Nyx()
        self.atlas = Atlas(self.llm)
        self.argus = Argus()
        self.phoenix = Phoenix()
        self.leviathan = Leviathan(settings)
        self.is_crypto = "USD" in settings.get("exchange", {}).get("symbol", "") or \
                         "USDT" in settings.get("exchange", {}).get("symbol", "")

    def _build_executor(self):
        mode = self.mode
        if mode in ("paper", "backtest"):
            return PaperExecutor()
        # demo (testnet) atau live -> cek akun aktif dulu, fallback ke env (settings)
        ak = sk = ""
        testnet = (mode == "demo")
        try:
            from core.accounts import active_account
            acc = active_account()
            if acc and acc.get("mode") == mode:
                ak, sk = acc.get("key", ""), acc.get("secret", "")
        except Exception:
            pass
        if not ak or not sk:
            key_map = self.s.get("api_keys", {}).get(mode, {})
            ak = os.environ.get(key_map.get("key_env", ""), "")
            sk = os.environ.get(key_map.get("secret_env", ""), "")
        if not ak or not sk:
            # tanpa key, fallback paper agar tidak crash
            return PaperExecutor()
        return ExchangeExecutor(self.s["exchange"]["id"], ak, sk, testnet=testnet)

    def _load_lessons(self, n: int = 5) -> str:
        """Memory lintas-waktu (adaptasi TradingAgents 'past_context').
        Gabung 2 sumber:
          - logs/trade_log.json  (OUTCOME: WIN/LOSS tiap trade)
          - logs/cycle_memory.json (KONTEKS: regime, sentimen, skor konsensus, equity)
        Atlas baca ini -> tidak amnesia, bisa bandingkan keputusan lalu vs hasil."""
        try:
            import json, os
            parts = []
            # --- outcome trade ---
            pt = "logs/trade_log.json"
            if os.path.exists(pt):
                arr = json.load(open(pt))
                for t in arr[-n:]:
                    pnl = t.get("pnl", 0.0)
                    tag = "WIN" if pnl > 0 else "LOSS"
                    parts.append(f"{tag} {t.get('symbol')} {t.get('strategy')} {pnl:+.1f}")
            # --- konteks cycle (kondisi pasar saat keputusan) ---
            pc = "logs/cycle_memory.json"
            if os.path.exists(pc):
                arr = json.load(open(pc))
                for c in arr[-n:]:
                    cs = c.get("consensus", {})
                    parts.append(
                        f"[{c.get('action')}] regim={c.get('regime')} sent={c.get('sentiment')} "
                        f"conf={cs.get('confidence')} final={cs.get('final')} eq={c.get('equity')}")
            return "; ".join(parts)
        except Exception:
            return ""

    def _record_trade(self, symbol, side, strategy, pnl):
        """Simpan outcome tiap trade -> logs/trade_log.json (memory)."""
        try:
            import json, os
            p = "logs/trade_log.json"
            arr = json.load(open(p)) if os.path.exists(p) else []
            arr.append({"ts": int(__import__("time").time()), "symbol": symbol,
                        "side": side, "strategy": strategy, "pnl": round(float(pnl), 2)})
            json.dump(arr[-200:], open(p, "w"))
        except Exception:
            pass

    def _save_cycle_memory(self, out: dict, consensus: dict, regime: str, psych_label: str):
        """Memory konteks lintas-waktu (adaptasi TradingAgents 'past_context').
        Simpan ringkasan tiap cycle: skor konsensus, regime, sentimen, + tiap agent text.
        Atlas baca ini di cycle berikutnya -> tidak amnesia."""
        try:
            import json, os
            p = "logs/cycle_memory.json"
            arr = json.load(open(p)) if os.path.exists(p) else []
            rec = {
                "ts": int(__import__("time").time()),
                "action": out.get("action"),
                "regime": regime,
                "sentiment": psych_label,
                "consensus": {k: consensus.get(k) for k in ("decision", "confidence",
                                                           "analyst_score", "risk_score", "final")},
                "positions": len(self.state.get("positions", [])),
                "equity": round(float(self.state.get("equity", 0.0)), 2),
                "realized_pnl": round(float(self.state.get("realized_pnl", 0.0)), 2),
                "agents": {s["key"]: s.get("text", "")[:200] for s in out.get("sections", [])},
            }
            arr.append(rec)
            json.dump(arr[-200:], open(p, "w"))
        except Exception:
            pass

    def run(self) -> str:
        out = self.run_structured()
        # audit log
        self._audit(out["briefing_text"])
        return out["briefing_text"]

    def run_structured(self) -> dict:
        """Sama seperti run(), tapi kembalikan dict terstruktur + tulis briefing.json.
        Multi-symbol: scan N token via screener, eksekusi HANYA yang skor tertinggi
        & sinyal valid (presisi) — SEKARANG: semua top-N yang valid (high-throughput).
        """
        ex = self.s.get("exchange", {})
        tf = ex.get("timeframe", "1h")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        if self.breaker.halted:
            msg = f"⛔ Bot HALT (circuit breaker): {self.breaker.halt_reason}\nTidak ada aksi sampai di-resume manual."
            send(msg, self.s)
            return msg

        # 0. data makro/regim (Chronos) — sekali pakai buat modulate
        macro = next_events()
        psych = {}      # lapisan sentimen eksternal (bukan RSI/MA)
        gglobal = {}
        if self.mock:
            fg = {"value": 30, "classification": "Fear"}
            psych = {"score": -10, "label": "neutral", "parts": ["mock"], "trending": []}
            btc_df = add_indicators(self.market.ohlcv("BTC/USDT", tf, 200)) if hasattr(self.market, "ohlcv") else None
        else:
            fg = fear_greed() if self.is_crypto else {}
            try:
                psych = market_psychology() if self.is_crypto else {}
            except Exception:
                psych = {}
            try:
                gglobal = coingecko_global() if self.is_crypto else {}
            except Exception:
                gglobal = {}
            btc_df = None
            try:
                btc_df = add_indicators(self.market.ohlcv("BTC/USDT", tf, 200))
            except Exception:
                btc_df = None
        vol = None
        if btc_df is not None and not btc_df.empty and "close" in btc_df.columns:
            try:
                vol = float(btc_df["close"].pct_change().tail(24).std() or 0.0)
            except Exception:
                vol = None
        chronos = self.chronos.analyze(macro, fg, btc_df, vol, gglobal, psych)
        chronos_txt = chronos.get("text", "") if isinstance(chronos, dict) else str(chronos)
        regime = (chronos.get("regime", "neutral") if isinstance(chronos, dict) else "neutral")

        # 1. SCREENER — cari setup terbaik dari banyak token
        top = screen(self.market, self.s, top_n=8, max_scan=50, mock=self.mock)
        best = top[0] if top else None
        symbol = best["symbol"] if best else ex.get("symbol", "BTC/USDT")

        # 2. DATA untuk token terpilih (utk briefing)
        if self.mock:
            from data.mock import mock_ohlcv
            df = add_indicators(mock_ohlcv(200))
            last = float(df.iloc[-1]["close"])
        else:
            df = add_indicators(self.market.ohlcv(symbol, tf, 200))
            last = self.market.last_price(symbol)
        helios = self.helios.analyze(df)
        bias = helios.get("bias", "n/a")

        # 3. VEGA (quant & crypto sentiment + statistik + tren viral)
        vega_txt = self.vega.analyze(fg, df, psych, psych.get("trending") if psych else None) \
            if self.is_crypto else "(bukan aset crypto — lewati)"

        # 4. ARGUS (market surveillance) — scan token terpilih
        argus_scan = self.argus.scan(df, symbol)
        argus_txt = self.argus.watchlist(top)

        eleanor_txt = ""
        fill_info = ""
        trade_action = "hold"
        exited_this_cycle = False

        # === CONSENSUS (adaptasi TradingAgents: bull/bear debate + risk voices + PM) ===
        # votes dibangun dari output agent yg SUDA ada (deterministik, no LLM)
        analyst_votes = []
        # Helios = bull voice (trend)
        if helios.get("bias") == "Bullish":
            analyst_votes.append({"name": "HELIOS", "view": "bull", "weight": 0.6,
                                  "note": helios.get("text", "")[:80]})
        elif helios.get("bias") == "Bearish":
            analyst_votes.append({"name": "HELIOS", "view": "bear", "weight": 0.6,
                                  "note": helios.get("text", "")[:80]})
        else:
            analyst_votes.append({"name": "HELIOS", "view": "hold", "weight": 0.3, "note": "netral"})
        # Vega = bear/quant voice (skew/sharpe)
        vs = self.vega.stats(df)
        if vs.get("sharpe", 0) < -1 or vs.get("skew", 0) < -0.5:
            analyst_votes.append({"name": "VEGA", "view": "bear", "weight": 0.5,
                                  "note": f"sharpe {vs['sharpe']} skew {vs['skew']} (ekor kiri)"})
        else:
            analyst_votes.append({"name": "VEGA", "view": "bull", "weight": 0.4,
                                  "note": f"sharpe {vs['sharpe']} vol {vs['vol']}"})
        # Chronos regime -> bull/bear
        if regime == "risk_on":
            analyst_votes.append({"name": "CHRONOS", "view": "bull", "weight": 0.4,
                                  "note": f"regim {regime}"})
        elif regime == "risk_off":
            analyst_votes.append({"name": "CHRONOS", "view": "bear", "weight": 0.4,
                                  "note": f"regim {regime}"})

        # risk voices
        risk_votes = []
        # Nyx = conservative (selalu hati-hati)
        risk_votes.append({"name": "NYX", "view": "bear", "weight": 0.5,
                          "note": "R:R>=2, 1% risk, circuit breaker"})
        # Leviathan = aggressive (mau masuk)
        risk_votes.append({"name": "LEVIATHAN", "view": "bull", "weight": 0.4,
                          "note": "signal engine ingin entry"})
        # Atlas = neutral PM (netral secara default)
        risk_votes.append({"name": "ATLAS", "view": "hold", "weight": 0.3, "note": "head strategist"})

        # lessons dari trade log (memory sederhana)
        lessons = self._load_lessons()
        consensus = decide_consensus(analyst_votes, risk_votes, lessons)
        atlas_txt_cm = consensus_summarize(consensus)
        # 8. PHOENIX (recovery) — cek fase drawdown
        phoenix = self.phoenix.assess(self.state.get("equity", 0.0),
                                       self.state.get("realized_pnl", 0.0))
        # scale ukuran posisi kalau recovery
        if phoenix.get("scale", 1.0) < 1.0:
            self.risk.position_scale = phoenix["scale"]

        # === MANAJEMEN EXIT dulu (per posisi) ===
        for pos in list(self.state["positions"]):
            psym = pos["symbol"]
            if self.mock:
                pl = float(add_indicators(mock_ohlcv(200)).iloc[-1]["close"])
            elif self.exec.paper:
                pl = last
            else:
                try:
                    pl = self.market.last_price(psym)
                except Exception:
                    pl = last
            exit_side = "sell" if pos["side"] == "buy" else "buy"
            reason = None
            pos["bars"] = pos.get("bars", 0) + 1   # naikkan tiap siklus (buat timeout)
            if pos["side"] == "buy":
                if pl <= pos["stop_loss"]:
                    reason = "SL"
                elif pl >= pos["take_profit"]:
                    reason = "TP"
            else:
                if pl >= pos["stop_loss"]:
                    reason = "SL"
                elif pl <= pos["take_profit"]:
                    reason = "TP"
            max_bars = int(self.s.get("risk", {}).get("max_hold_bars", 48))
            if reason is None and (pos.get("bars", 0) + 1) >= max_bars:
                reason = "TIMEOUT"
            if reason:
                fill = self.exec.close(psym, exit_side, pos["qty"], pl)
                pnl = (fill.price - pos["entry"]) * pos["qty"] if pos["side"] == "buy" else (pos["entry"] - fill.price) * pos["qty"]
                self.state["equity"] += pnl
                self.state["realized_pnl"] += pnl
                self.state["positions"].remove(pos)
                fill_info += f"\nEXIT {reason}: {exit_side} {pos['qty']:.6f} {psym} @ {fill.price:.2f} | PnL {pnl:+.2f}"
                trade_action = f"exit_{reason.lower()}"
                exited_this_cycle = True
                self.breaker.check(self.risk.daily_loss_breached(self.state["realized_pnl"]))

        # === ENTRY — SEMUA top-N yang sinyal valid & masih bisa buka ===
        new_entries = 0
        for r in top:
            if new_entries >= 8:
                break
            if len(self.state["positions"]) >= self.risk.max_open:
                break
            sym = r["symbol"]
            try:
                if self.mock:
                    sdf = add_indicators(mock_ohlcv(200, seed=hash(sym) % 1000))
                else:
                    sdf = add_indicators(self.market.ohlcv(sym, tf, 200))
                    if sdf is None or sdf.empty:
                        continue
                slast = float(sdf.iloc[-1]["close"]) if self.mock else self.market.last_price(sym)
            except Exception:
                continue
            sig = self.leviathan.generate_signal(sdf, slast)
            if not sig or sig.get("side") not in ("buy", "sell"):
                continue
            # filter sentimen eksternal (bukan RSI/MA) — tolak long kalau bearish ekstrem
            if not self.vega.sentiment_ok(psych, sig.get("side")):
                fill_info += f"\nSKIP {sym}: sentimen bearish ekstrem (Vega)"
                continue
            # jangan dobel di simbol yg sudah ada
            if any(p["symbol"] == sym for p in self.state["positions"]):
                continue
            t = ProposedTrade(sym, sig["side"], sig["entry"],
                              sig["stop_loss"], sig["take_profit"], sig["conviction"])
            trade_ok, rr_msg = self.risk.validate(t)
            can_open, open_msg = self.risk.can_open_new(len(self.state["positions"]))
            if trade_ok and can_open:
                qty = self.risk.position_size(t) * consensus.get("sizing_mult", 1.0)
                if qty <= 0:
                    continue
                fill = self.exec.execute(sym, sig["side"], qty, sig["entry"])
                self._record_trade(sym, sig["side"], sig.get("strategy", "?"), 0.0)
                self.state["positions"].append({
                    "symbol": sym, "side": sig["side"], "qty": qty,
                    "entry": fill.price, "stop_loss": sig["stop_loss"],
                    "take_profit": sig["take_profit"], "bars": 0,
                })
                fill_info += f"\n{'PAPER' if fill.paper else 'LIVE'} FILL: {sig['side']} {qty:.6f} {sym} @ {fill.price:.2f} ({sig.get('strategy','?')}) [consensus conf={consensus.get('confidence')}]"
                trade_action = "entry"
                new_entries += 1

        if not fill_info:
            fill_info = "Sinyal: HOLD (RSI netral / tidak ada setup bagus)."

        import time as _t
        self.state["last_cycle_ts"] = int(_t.time())
        save_state(self.state)

        # equity curve point (pantau PnL)
        try:
            import time
            from core.equity import record as eq_record
            eq_record(self.state.get("equity", 0), self.state.get("realized_pnl", 0),
                      len(self.state.get("positions", [])), int(time.time()))
        except Exception:
            pass

        # 7. ATLAS (head strategist) — dari state NYATA + sintesis
        atlas_txt = self.atlas.reflect({
            "realized_pnl": self.state.get("realized_pnl", 0.0),
            "equity": self.state.get("equity", 0.0),
            "balance": self.risk.balance,
            "open_positions": len(self.state.get("positions", [])),
            "max_open": self.risk.max_open,
        }) + "\n\n" + atlas_txt_cm

        # 8. RENDER BRIEFING
        eleanor_txt = self.nyx.comment(
            trade_action in ("entry",) or exited_this_cycle,
            f"Regim: {regime.upper()}",
            len(self.state["positions"]), self.risk.max_open,
            halted=self.breaker.halted,
            daily_loss_pct=abs(self.state.get("realized_pnl", 0.0))) if not eleanor_txt else eleanor_txt
        sections = [
            {"key": "atlas",    "name": "ATLAS",        "role": "Head Strategist",   "text": atlas_txt},
            {"key": "chronos",  "name": "CHRONOS",      "role": "Macro Timing",      "text": chronos_txt},
            {"key": "helios",   "name": "HELIOS",       "role": "Trend Analyst",     "text": helios.get("text", "")},
            {"key": "vega",     "name": "VEGA",         "role": "Quant & Statistics", "text": vega_txt},
            {"key": "leviathan","name": "LEVIATHAN",    "role": "Signal/Execution",  "text": f"entries={new_entries} top_setup={symbol} strategy=rsi+breakout"},
            {"key": "nyx",      "name": "NYX",          "role": "Risk Guardian",     "text": f"{eleanor_txt}\n{fill_info}"},
            {"key": "argus",    "name": "ARGUS",        "role": "Market Surveillance","text": argus_txt},
            {"key": "phoenix",  "name": "PHOENIX",      "role": "Recovery",          "text": f"[{phoenix.get('status','?').upper()}] dd={phoenix.get('dd_pct',0)}% — {phoenix.get('advice','')}"},
        ]
        screen_txt = "\n".join(f"  {r['symbol']}: skor {r['score']} | RSI {r['rsi']} | {r['side_bias']}" for r in top)
        briefing_text = (
            f"┌─ 📋 TRADING DESK BRIEFING — {now} ─┐\n"
            f"│ TOP SETUP: {symbol} | TF: {tf} | BIAS: {bias} | MODE: {self.s.get('mode')} | REGIM: {regime.upper()}\n"
            f"│ Open: {len(self.state['positions'])} | Equity: {self.state.get('equity',0):.2f} | PnL: {self.state.get('realized_pnl',0):+.2f}\n"
            f"│ Screener top-{len(top)}:\n{screen_txt}\n\n"
            + "\n\n".join(f"🔷 {s['name']} ({s['role']})\n   → {s['text']}" for s in sections)
            + f"\n\n└─ ⚠️ DISCLAIMER: Bukan nasihat keuangan. ─┘"
        )
        out = {
            "timestamp": now,
            "asset": symbol,
            "timeframe": tf,
            "bias": bias,
            "regime": regime,
            "mode": self.s.get("mode"),
            "signal": {"side": trade_action},
            "action": trade_action,
            "equity": round(self.state.get("equity", 0), 2),
            "realized_pnl": round(self.state.get("realized_pnl", 0), 2),
            "open_positions": len(self.state.get("positions", [])),
            "screener": top,
            "halted": self.breaker.halted,
            "sections": sections,
            "briefing_text": briefing_text,
        }
        self._write_json(out)
        send(briefing_text, self.s)
        # snapshot pasar (chart) + akun demo (real trades) untuk dashboard
        try:
            scan_syms = [r["symbol"] for r in top] + [symbol]
            market_snapshot(self.market, scan_syms, tf, 60)
        except Exception:
            pass
        try:
            account_snapshot(self.exec, scan_syms)
        except Exception:
            pass
        # simpan memory konteks lintas-waktu (Atlas baca di cycle berikutnya)
        try:
            self._save_cycle_memory(out, consensus, regime,
                                    (psych or {}).get("label", "n/a"))
        except Exception:
            pass
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
