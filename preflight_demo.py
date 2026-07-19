#!/usr/bin/env python
"""Preflight guard: refuse to start bot unless mode is DEMO on both settings + active account.
Exit 0 = safe (demo). Exit 1 = BLOCKED (live/unsafe). Used by auto-start launcher."""
import json, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))

def fail(msg):
    print("[PREFLIGHT] BLOCKED:", msg)
    sys.exit(1)

# 1. settings.yaml mode must be demo
sy = os.path.join(ROOT, "config", "settings.yaml")
mode_line = None
with open(sy, encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if s.startswith("mode:"):
            mode_line = s.split(":", 1)[1].strip().strip('"').strip("'")
            break
if mode_line is None:
    fail("settings.yaml has no top-level 'mode:'")
if mode_line.lower() != "demo":
    fail(f"settings.yaml mode='{mode_line}' (must be 'demo')")

# 2. active account in accounts.json must be mode demo
aj = os.path.join(ROOT, "config", "accounts.json")
d = json.load(open(aj, encoding="utf-8"))
active = d.get("active")
accs = d.get("accounts", [])
if isinstance(accs, dict):
    accs = list(accs.values())
match = [x for x in accs if x.get("name") == active]
if not match:
    fail(f"active account '{active}' not found in accounts list")
amode = match[0].get("mode", "?")
if amode.lower() != "demo":
    fail(f"active account '{active}' mode='{amode}' (must be 'demo')")

print(f"[PREFLIGHT] OK - settings.mode=demo, active='{active}' mode=demo. Safe to start bot.")
sys.exit(0)
