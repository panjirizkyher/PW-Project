"""
MAIN — entry point Trading Desk autonomous.
Usage:
  python main.py            # loop sesuai schedule (run_every_minutes)
  python main.py --once     # jalan satu kali (buat test)
"""
from __future__ import annotations
import sys
import time
import yaml

from core.orchestrator import Orchestrator


def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    settings = load_settings()
    mock = "--mock" in sys.argv
    orch = Orchestrator(settings, mock=mock)

    if "--once" in sys.argv:
        print(orch.run())
        return

    interval = int(settings.get("schedule", {}).get("run_every_minutes", 60)) * 60
    print(f"[TRADING DESK] autonomous loop — tiap {interval}s. Ctrl+C untuk berhenti.")
    try:
        while True:
            try:
                print(orch.run())
            except Exception as e:
                print(f"[LOOP] error: {e}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[TRADING DESK] dihentikan oleh user.")


if __name__ == "__main__":
    main()
