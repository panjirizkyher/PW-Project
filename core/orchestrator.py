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
import time
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
from core.ml.regime_detector import RegimeDetector, _feat_row
from core.ml.signal_filter import SignalFilter
from notify.telegram import send
from notify.agent import trade_alert, risk_warning, maybe_daily_report


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
        # kalau breaker halted, run_structured balikin STRING (bukan dict)
        if isinstance(out, str):
            return out
        # audit log
        self._audit(out["briefing_text"])
        return out["briefing_text"]

    def _log_event(self, msg: str):
        """Tulis event ke logs/bot_debug.log + stdout (aman, tdk crash)."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        try:
            os.makedirs("logs", exist_ok=True)
            with open("logs/bot_debug.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        print(line)

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
                # full sentiment (VADER + RSS headlines) untuk dashboard + audit
                sent_full = {}
                try:
                    from core.ml.sentiment import news_sentiment
                    sent_full = news_sentiment() if self.is_crypto else {}
                except Exception:
                    pass
                try:
                    import json as _js
                    os.makedirs("logs", exist_ok=True)
                    _js.dump({"ts": int(time.time()), "psych": psych,
                              "sentiment": sent_full, "fg": fg},
                             open("logs/sentiment.json", "w"), ensure_ascii=False)
                except Exception:
                    pass
                # kirim ke agent bertugas (Vega/Convinced) — sudah lewat `psych` arg
                self._log_event(f"SENTIMENT: score={sent_full.get('score_0_100')} "
                                f"n_articles={sent_full.get('n_articles')} "
                                f"pos={sent_full.get('top_positive', [])[:2]} "
                                f"neg={sent_full.get('top_negative', [])[:2]}")
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

        # 0b. ML REGIME DETECTION (Learning Agent) — klasifikasi market mandiri.
        # Override regime makro dgn prediksi ML dari fitur LIVE (btc_df + F&G + breadth).
        regime_ml = regime
        ml_regime_label = ""
        ml_conf = 0.0
        try:
            rdet, _ = RegimeDetector.load()
            fgv = (fg or {}).get("value") if isinstance(fg, dict) else None
            br = (psych or {}).get("score")
            br = (br + 100) / 200.0 if isinstance(br, (int, float)) else 0.5  # -100..100 -> 0..1
            ddom = (gglobal or {}).get("btc_dominance_change_24h") if isinstance(gglobal, dict) else None
            frow = _feat_row(btc_df, fg_value=fgv, breadth=br, dom_delta=ddom)
            if frow:
                pr = rdet.predict(frow)
                if pr.get("trained"):
                    regime_ml = pr["regime"]
                    ml_regime_label = pr["label"]
                    ml_conf = pr["confidence"]
        except Exception:
            pass
        # ambil param optimal utk regime tsb (falls back ke default)
        from core.ml.parameter_optimizer import params_for_regime, load_params
        ml_params = params_for_regime(regime_ml, load_params())


        # 1. SCREENER — cari setup terbaik dari banyak token (HFT scale: scan, top 16)
        # Cache screener 30s biar cycle 2s tdk spam Binance (anti rate-limit).
        cache_s = int((self.s.get("hft", {}) or {}).get("screener_cache_seconds", 30))
        now_ts = int(time.time())
        if getattr(self, "_scan_cache", None) and (now_ts - self._scan_cache_ts) < cache_s:
            top = self._scan_cache
        else:
            max_scan = int((self.s.get("hft", {}) or {}).get("max_scan", 150))
            top = screen(self.market, self.s, top_n=16, max_scan=max_scan,
                         mock=self.mock, max_workers=16)
            self._scan_cache = top
            self._scan_cache_ts = now_ts
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
            analyst_votes.append({"name": "SKAY", "view": "bull", "weight": 0.6,
                                  "note": helios.get("text", "")[:80]})
        elif helios.get("bias") == "Bearish":
            analyst_votes.append({"name": "SKAY", "view": "bear", "weight": 0.6,
                                  "note": helios.get("text", "")[:80]})
        else:
            analyst_votes.append({"name": "SKAY", "view": "hold", "weight": 0.3, "note": "netral"})
        # Vega = bear/quant voice (skew/sharpe)
        vs = self.vega.stats(df)
        if vs.get("sharpe", 0) < -1 or vs.get("skew", 0) < -0.5:
            analyst_votes.append({"name": "ABRISAM", "view": "bear", "weight": 0.5,
                                  "note": f"sharpe {vs['sharpe']} skew {vs['skew']} (ekor kiri)"})
        else:
            analyst_votes.append({"name": "ABRISAM", "view": "bull", "weight": 0.4,
                                  "note": f"sharpe {vs['sharpe']} vol {vs['vol']}"})
        # Chronos regime -> bull/bear
        if regime == "risk_on":
            analyst_votes.append({"name": "WIRA", "view": "bull", "weight": 0.4,
                                  "note": f"regim {regime}"})
        elif regime == "risk_off":
            analyst_votes.append({"name": "WIRA", "view": "bear", "weight": 0.4,
                                  "note": f"regim {regime}"})

        # risk voices — AGRESIF: bobot bull dinaikkan, bear diturunkan
        risk_votes = []
        # Nyx = conservative (diturunkan biar tdk selalu HOLD)
        risk_votes.append({"name": "QUEEN", "view": "bear", "weight": 0.25,
                          "note": "R:R>=1.8, circuit breaker tetap ON"})
        # Leviathan = aggressive (dinaikkan biar lebih sering entry)
        risk_votes.append({"name": "SYAFIRA", "view": "bull", "weight": 0.7,
                          "note": "signal engine ingin entry (agresif)"})
        # Atlas = neutral PM (netral secara default)
        risk_votes.append({"name": "PANJI", "view": "hold", "weight": 0.2, "note": "head strategist"})

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
                # paper: pakai harga posisi sendiri (bukan global 'last' token lain!)
                pl = pos.get("last") or pos.get("entry")
            else:
                try:
                    pl = self.market.last_price(psym)
                except Exception:
                    pl = pos.get("last") or pos.get("entry")
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
                try:
                    fill = self.exec.close(psym, exit_side, pos["qty"], pl)
                except PermissionError as e:
                    self._log_event(f"EXIT_BLOCKED {psym}: {e}")
                    fill_info += f"\nTIDAK EXIT {psym}: {e}"
                    continue
                pnl = (fill.price - pos["entry"]) * pos["qty"] if pos["side"] == "buy" else (pos["entry"] - fill.price) * pos["qty"]
                self.state["equity"] += pnl
                self.state["realized_pnl"] += pnl
                # catat exit ke trade_log (sebelumnya cuma entry yg di-log -> count stale)
                self._record_trade(psym, exit_side, pos.get("strategy", "?"), pnl)
                self.state["positions"].remove(pos)
                fill_info += f"\nEXIT {reason}: {exit_side} {pos['qty']:.6f} {psym} @ {fill.price:.2f} | PnL {pnl:+.2f}"
                # NOTIFY: Trade Alert EXIT + P/L detail (instan ke HP)
                try:
                    trade_alert("exit", psym, exit_side, fill.price, pos["qty"],
                                strategy=pos.get("strategy", "?"), pnl=pnl, settings=self.s)
                except Exception:
                    pass
                trade_action = f"exit_{reason.lower()}"
                exited_this_cycle = True
                self.breaker.check(self.risk.daily_loss_breached(self.state["realized_pnl"]))

        # === ENTRY — SEMUA top-N yang sinyal valid & masih bisa buka (HFT: sampai 16) ===
        new_entries = 0
        for r in top:
            if new_entries >= 16:
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
            # 0c. HYBRID GATE (Learning Agent B): Convinced Score > 85%
            # Gabungan TEKNIKAL + SENTIMEN + ML PROB. Hanya trade yg sangat
            # yakin yg lolos ke Execution Agent (instruksi Hybrid B).
            try:
                from core.ml.convinced_score import get_scorer
                sfilter, _ = SignalFilter.load()
                ema_gap = 0.0
                if "ema50" in sdf.columns and "ema200" in sdf.columns:
                    e50 = float(sdf.iloc[-1]["ema50"]); e200 = float(sdf.iloc[-1]["ema200"])
                    ema_gap = (e50 - e200) / max(e200, 1e-9) if e200 else 0.0
                fgv = ((fg or {}).get("value", 50) if isinstance(fg, dict) else 50)
                setup_feat = {
                    "rr": float(sig.get("reward_risk", sig.get("conviction", 0.5) * 2.5)),
                    "conviction": float(sig.get("conviction", 0.5)),
                    "rsi": float(sdf.iloc[-1]["rsi14"]) if "rsi14" in sdf.columns else 50.0,
                    "atr_pct": float(sdf.iloc[-1]["atr14"] / max(sdf.iloc[-1]["close"], 1e-9)) if "atr14" in sdf.columns else 0.03,
                    "ema_gap": ema_gap,
                    "fg_norm": fgv / 100.0,
                    "regime_code": {"trend_up": 0.0, "trend_down": 1.0, "range": 2.0,
                                    "volatile": 3.0, "panic": 4.0}.get(regime_ml, 2.0),
                    "side_code": 1.0 if sig.get("side") == "buy" else 0.0,
                }
                scorer = get_scorer(threshold=0.85)
                cs = scorer.score(sdf, sig, fg_value=fgv, psych=psych,
                                 sfilter=sfilter, setup_feat=setup_feat, symbol=sym)
                if not cs["passes"]:
                    fill_info += f"\nSKIP CONVINCED {sym}: score {cs['score_pct']}% < {cs['threshold_pct']}% (T{s['technical']} S{s['sentiment']} ML{s['ml']})"
                    continue
            except Exception:
                # fail-open: kalau scorer error, tetap lanjut ke gate NYX (jgn blokir buta)
                pass
            # filter sentimen eksternal (bukan RSI/MA) — AGRESIF: cuma tolak
            # long kalau F&G < 15 (panic total), biar tdk lewat SKIP saat fear wajar
            if not self.vega.sentiment_ok(psych, sig.get("side")):
                fgv = (psych or {}).get("fg_value", 100) if isinstance(psych, dict) else 100
                if fgv < 15:
                    fill_info += f"\nSKIP {sym}: sentimen panic ekstrem (F&G {fgv})"
                    continue
                # F&G >=15 -> abaikan filter (agresif, tetap masuk)
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
                try:
                    fill = self.exec.execute(sym, sig["side"], qty, sig["entry"])
                except PermissionError as e:
                    fill_info += f"\nTIDAK TRADE {sym}: {e}"
                    self._log_event(f"TRADE_BLOCKED {sym}: {e}")
                    continue
                self._record_trade(sym, sig["side"], sig.get("strategy", "?"), 0.0)
                self.state["positions"].append({
                    "symbol": sym, "side": sig["side"], "qty": qty,
                    "entry": fill.price, "stop_loss": sig["stop_loss"],
                    "take_profit": sig["take_profit"], "bars": 0,
                    "last": fill.price,
                })
                fill_info += f"\n{'PAPER' if fill.paper else 'LIVE'} FILL: {sig['side']} {qty:.6f} {sym} @ {fill.price:.2f} ({sig.get('strategy','?')}) [consensus conf={consensus.get('confidence')}]"
                # NOTIFY: Trade Alert ENTRY (instan ke HP)
                try:
                    trade_alert("entry", sym, sig["side"], fill.price, qty,
                                strategy=sig.get("strategy", "?"), settings=self.s)
                except Exception:
                    pass
                trade_action = "entry"
                new_entries += 1

        if not fill_info:
            fill_info = "Sinyal: HOLD (RSI netral / tidak ada setup bagus)."

        import time as _t
        self.state["last_cycle_ts"] = int(_t.time())

        # recalc equity agar wajar (bukan ngaco):
        # equity = base_balance + realized_pnl + sum(unrealized per posisi)
        # pakai harga LIVE (market.last_price), bukan pos["last"] yg stale
        try:
            base = float(self.risk.balance)
            unreal = 0.0
            for pos in self.state.get("positions", []):
                try:
                    lp = float(self.market.last_price(pos["symbol"]))
                    pos["last"] = lp   # simpan harga live (Fix A) hanya kalau sukses
                except Exception:
                    lp = pos.get("last", pos.get("entry", 0))
                if pos["side"] == "buy":
                    unreal += (lp - pos["entry"]) * pos["qty"]
                else:
                    unreal += (pos["entry"] - lp) * pos["qty"]
            self.state["equity"] = base + float(self.state.get("realized_pnl", 0.0)) + unreal
        except Exception:
            pass
        save_state(self.state)

        # equity curve point (pantau PnL)
        try:
            from core.equity import record as eq_record
            eq_record(self.state.get("equity", 0), self.state.get("realized_pnl", 0),
                      len(self.state.get("positions", [])), int(time.time()))
        except Exception:
            pass

        # 6b. NOTIFY: Risk Warning (volatilitas ekstrem / drawdown / circuit halt)
        try:
            eq_now = float(self.state.get("equity", 0.0))
            base = float(self.risk.balance)
            dd_pct = (base - eq_now) / base * 100.0 if base > 0 else 0.0
            if self.breaker.halted:
                risk_warning("⛔ CIRCUIT BREAKER HALT",
                             f"Bot dihentikan sementara. Equity {eq_now:,.2f}", self.s)
            elif dd_pct >= float(self.s.get("risk", {}).get("max_daily_loss_pct", 12.0)) * 0.7:
                risk_warning("📉 DRAWDOWN TINGGI",
                             f"Equity {eq_now:,.2f} | DD {dd_pct:.1f}%", self.s)
            elif regime_ml in ("volatile", "panic"):
                risk_warning("🌪️ VOLATILITAS EKSTRIM",
                             f"Regime: {regime_ml.upper()} | DD {dd_pct:.1f}%", self.s)
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
            {"key": "atlas",    "name": "PANJI",    "role": "Head Strategist",   "text": atlas_txt},
            {"key": "chronos",  "name": "WIRA",     "role": "Macro Timing",      "text": chronos_txt},
            {"key": "helios",   "name": "SKAY",     "role": "Trend Analyst",     "text": helios.get("text", "")},
            {"key": "vega",     "name": "ABRISAM",  "role": "Quant & Statistics", "text": vega_txt},
            {"key": "leviathan","name": "SYAFIRA",  "role": "Signal/Execution",  "text": f"entries={new_entries} top_setup={symbol} strategy=rsi+breakout"},
            {"key": "nyx",      "name": "QUEEN",    "role": "Risk Guardian",     "text": f"{eleanor_txt}\n{fill_info}"},
            {"key": "argus",    "name": "NOAH",     "role": "Market Surveillance","text": argus_txt},
            {"key": "phoenix",  "name": "ARZANKA",  "role": "Recovery + Learning ML", "text": f"[{phoenix.get('status','?').upper()}] dd={phoenix.get('dd_pct',0)}% — {phoenix.get('advice','')}"},
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

        # 9. NOTIFY: Daily Report (1x/hari, dari Learning Agent)
        try:
            def _compute_daily_stats():
                st = self.state
                trades = []
                try:
                    trades = json.load(open("logs/trade_log.json"))
                except Exception:
                    trades = []
                pnls = [t.get("pnl", 0.0) for t in trades if "pnl" in t]
                best = max(pnls) if pnls else 0.0
                worst = min(pnls) if pnls else 0.0
                win = sum(1 for p in pnls if p > 0)
                wr = (win / len(pnls) * 100.0) if pnls else 0.0
                learn_note = ""
                try:
                    lr = self.phoenix.learn(
                        feature_rows=[], regime_dfs={}, trade_log_path="logs/trade_log.json")
                    learn_note = lr.get("advice", "") if isinstance(lr, dict) else ""
                except Exception:
                    learn_note = ""
                return {
                    "equity": float(st.get("equity", 0.0)),
                    "realized_pnl": float(st.get("realized_pnl", 0.0)),
                    "n_trades": len(pnls),
                    "win_rate": round(wr, 1),
                    "best": best, "worst": worst,
                    "open_positions": len(st.get("positions", [])),
                    "learning_note": learn_note,
                }
            maybe_daily_report(self.state, self.s, _compute_daily_stats)
        except Exception:
            pass

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
