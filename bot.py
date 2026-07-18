"""
SERVE — jalankan Trading Desk + dashboard live lokal.
Usage:
  python bot.py            # loop (tiap run_every_minutes) + price-feed + HTTP :8001
  python bot.py --once     # jalan 1x lalu serve (test cepat)
Buka browser: http://localhost:8001/dashboard.html

Endpoint tambahan:
  GET  /logs/tick.json        -> harga terbaru tiap token (price-feed, realtime)
  GET  /api/settings         -> settings saat ini (param yg bisa diubah)
  POST /api/settings         -> ubah param live (whitelist aman)
  POST /api/run              -> paksa jalankan siklus sekarang
"""
from __future__ import annotations
import sys, time, os, json, threading, yaml
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from core.env_loader import load_env
from core.orchestrator import Orchestrator


def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Param yg BOLEH diubah dari dashboard (whitelist). Nilai di luar ini ditolak.
EDITABLE = {
    "signal.rsi_oversold": float,
    "signal.rsi_overbought": float,
    "signal.target_reward_risk_ratio": float,
    "signal.rsi_period": int,
    "risk.min_reward_risk_ratio": float,
    "risk.max_open_positions": int,
    "risk.risk_per_trade_pct": float,
    "risk.max_daily_loss_pct": float,
    "risk.max_hold_bars": int,
    "risk.max_total_exposure_pct": float,
    "dashboard.refresh_seconds": int,
    "price_feed.refresh_seconds": int,
}


def set_nested(d: dict, path: str, val):
    keys = path.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = val


def get_nested(d: dict, path: str):
    cur = d
    for k in path.split("."):
        cur = cur.get(k, {})
    return cur


class Handler(SimpleHTTPRequestHandler):
    orch = None
    settings = None
    lock = threading.Lock()

    def _auth_ok(self) -> bool:
        tok = os.getenv("DASHBOARD_TOKEN", "")
        if not tok:
            return True  # auth dimatikan (mode lokal)
        sent = self.headers.get("X-Auth-Token", "")
        return sent == tok

    def _send(self, code: int, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Auth-Token")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ensure_settings(self):
        """Fallback: kalau Handler.settings None (mis. re-exec uv), load langsung.
        Pakai path ABSOLUT supaya cwd berubah (uv re-exec) tdk bikin gagal."""
        if Handler.settings is None:
            try:
                import os as _os
                _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                   "config", "settings.yaml")
                if not _os.path.exists(_p):
                    _p = "config/settings.yaml"
                Handler.settings = load_settings(_p)
            except Exception as _e:
                # debug: tulis kenapa gagal biar bisa diagnosa di child uv
                try:
                    with open("logs/bot_debug.log", "a", encoding="utf-8") as _f:
                        _f.write(f"[ensure_settings FAIL] {type(_e).__name__}: {_e}\n")
                except Exception:
                    pass
                Handler.settings = {}

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        self._ensure_settings()
        if self.path.startswith("/api/"):
            if not self._auth_ok():
                self._send(401, {"ok": False, "error": "unauthorized"})
                return
            if self.path.startswith("/api/settings"):
                editable = {k: get_nested(Handler.settings, k) for k in EDITABLE}
                self._send(200, {"editable": editable, "mode": Handler.settings.get("mode")})
                return
            self._send(404, {"ok": False})
            return
        # inject token ke dashboard biar API jalan dari mana aja
        if self.path in ("/dashboard.html", "/", ""):
            tok = os.getenv("DASHBOARD_TOKEN", "")
            if tok:
                try:
                    html = open("dashboard.html", "r", encoding="utf-8").read()
                    if "?t=" not in self.path and "DASHBOARD_TOKEN_INJECT" not in html:
                        html = html.replace("</head>",
                            f"<script>window.DTOK='{tok}';</script></head>")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                        self.end_headers()
                        self.wfile.write(html.encode("utf-8"))
                        return
                except Exception:
                    pass
        return super().do_GET()

    def do_POST(self):
        self._ensure_settings()
        if self.path.startswith("/api/"):
            if not self._auth_ok():
                self._send(401, {"ok": False, "error": "unauthorized"})
                return
            if self.path.startswith("/api/settings"):
                try:
                    ln = int(self.headers.get("Content-Length", 0))
                    raw = json.loads(self.rfile.read(ln) or b"{}")
                except Exception as e:
                    self._send(400, {"ok": False, "error": str(e)})
                    return
                changed = []
                with Handler.lock:
                    for k, v in raw.items():
                        if k not in EDITABLE:
                            continue
                        try:
                            v = EDITABLE[k](v)
                            set_nested(Handler.settings, k, v)
                            changed.append(k)
                        except Exception:
                            pass
                    # simpan ke yaml biar persist
                    try:
                        with open("config/settings.yaml", "w", encoding="utf-8") as f:
                            yaml.safe_dump(Handler.settings, f, allow_unicode=True, sort_keys=False)
                    except Exception:
                        pass
                self._send(200, {"ok": True, "changed": changed})
                return
            if self.path.startswith("/api/run"):
                try:
                    threading.Thread(target=Handler.orch.run, daemon=True).start()
                    self._send(200, {"ok": True, "msg": "siklus dijalankan"})
                except Exception as e:
                    self._send(500, {"ok": False, "error": str(e)})
                return
        self._send(404, {"ok": False})


def price_feed(orch: Orchestrator, interval: int):
    """Poll harga tiap interval detik -> logs/tick.json (realtime feel)."""
    print(f"[SERVE] price-feed — tiap {interval}s")
    from core.equity import record as eq_record
    while True:
        try:
            syms = []
            try:
                import json as _j
                m = _j.load(open("logs/market.json"))
                syms = list(m.keys())
            except Exception:
                pass
            if not syms:
                syms = [orch.s.get("exchange", {}).get("symbol", "BTC/USDT")]
            out = {}
            for sym in syms:
                try:
                    out[sym] = round(orch.market.last_price(sym), 2)
                except Exception:
                    pass
            os.makedirs("logs", exist_ok=True)
            with open("logs/tick.json", "w", encoding="utf-8") as f:
                _j.dump({"ts": int(time.time()), "prices": out}, f)
            # patch market.json candle terakhir biar chart ikut gerak (realtime feel)
            try:
                mp = "logs/market.json"
                if os.path.exists(mp):
                    m = _j.load(open(mp))
                    for sym, p in out.items():
                        if sym in m and m[sym].get("ohlc"):
                            m[sym]["ohlc"][-1][4] = p      # close terakhir
                            m[sym]["last"] = p
                    _j.dump(m, open(mp, "w"), ensure_ascii=False)
            except Exception:
                pass
            # equity point tiap tick (pantau PnL realtime)
            try:
                st = orch.state
                eq_record(st.get("equity", 0), st.get("realized_pnl", 0),
                          len(st.get("positions", [])), int(time.time()),
                          base_balance=orch.risk.balance)
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(interval)


def run_loop(orch: Orchestrator, interval: int):
    print(f"[SERVE] orchestrator loop — tiap {interval}s (Ctrl+C berhenti)")
    while True:
        try:
            orch.run()
        except Exception as e:
            print(f"[LOOP] error: {e}")
        time.sleep(interval)


def main():
    load_env()
    settings = load_settings()
    mock = "--mock" in sys.argv
    orch = Orchestrator(settings, mock=mock)
    interval = int(settings.get("schedule", {}).get("run_every_minutes", 60)) * 60
    port = int(os.getenv("PEWE_PORT") or settings.get("dashboard", {}).get("port", 8000))
    Handler.orch = orch
    Handler.settings = settings
    try:
        with open("logs/bot_debug.log", "a", encoding="utf-8") as _f:
            _f.write(f"[main] settings loaded, mode={settings.get('mode')} keys={list(settings.keys())}\n")
    except Exception:
        pass

    if "--once" in sys.argv:
        orch.run()
        print(f"[SERVE] --once selesai. Buka http://localhost:{port}/dashboard.html")

    # HTTP server
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"[SERVE] Dashboard: http://localhost:{port}/dashboard.html")

    # price-feed thread (realtime)
    pf_int = int(settings.get("price_feed", {}).get("refresh_seconds", 5))
    threading.Thread(target=price_feed, args=(orch, pf_int), daemon=True).start()

    if "--once" not in sys.argv:
        run_loop(orch, interval)
    else:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.shutdown()
            print("\n[SERVE] dihentikan.")


if __name__ == "__main__":
    main()
