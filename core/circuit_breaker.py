"""
CIRCUIT BREAKER — stop otomatis saat kondisi berbahaya.
State disimpan di file agar persist antar run.
"""
from __future__ import annotations
import json
import os
from datetime import date


class CircuitBreaker:
    def __init__(self, state_path: str = "logs/circuit_state.json"):
        self.state_path = state_path
        self.halted = False
        self.halt_reason = ""
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, "r") as f:
                    s = json.load(f)
                # reset halt tiap hari baru
                if s.get("date") == str(date.today()):
                    self.halted = s.get("halted", False)
                    self.halt_reason = s.get("reason", "")
        except Exception:
            self.halted = False

    def _save(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump({"date": str(date.today()), "halted": self.halted,
                       "reason": self.halt_reason}, f)

    def halt(self, reason: str):
        self.halted = True
        self.halt_reason = reason
        self._save()
        print(f"[CIRCUIT BREAKER] HALT: {reason}")

    def resume(self):
        self.halted = False
        self.halt_reason = ""
        self._save()

    def check(self, loss_breached: tuple[bool, str]):
        breached, msg = loss_breached
        if breached:
            self.halt(msg)
        return self.halted
