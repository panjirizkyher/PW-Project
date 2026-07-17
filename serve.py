"""
SERVE — jalankan Trading Desk + dashboard live lokal.
Usage:
  python serve.py            # loop (tiap run_every_minutes) + HTTP di :8000
  python serve.py --once     # jalan 1x lalu serve (untuk test cepat)
Buka browser: http://localhost:8000/dashboard.html
"""
from __future__ import annotations
import sys
import time
import os
import yaml
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading

from core.env_loader import load_env
from core.orchestrator import Orchestrator


def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=os.getcwd(), **kw)

    def log_message(self, *a):
        pass  # senyap


def run_loop(orch: Orchestrator, interval: int):
    print(f"[SERVE] orchestrator loop — tiap {interval}s (Ctrl+C berhenti)")
    try:
        while True:
            try:
                orch.run()
            except Exception as e:
                print(f"[LOOP] error: {e}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[SERVE] dihentikan.")


def main():
    load_env()
    settings = load_settings()
    mock = "--mock" in sys.argv
    orch = Orchestrator(settings, mock=mock)
    interval = int(settings.get("schedule", {}).get("run_every_minutes", 60)) * 60
    port = int(settings.get("dashboard", {}).get("port", 8000))

    if "--once" in sys.argv:
        orch.run()
        print(f"[SERVE] --once selesai. Buka http://localhost:{port}/dashboard.html")

    # HTTP server (thread) melayani dashboard.html + logs/briefing.json
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"[SERVE] Dashboard: http://localhost:{port}/dashboard.html")

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
