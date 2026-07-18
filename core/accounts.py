"""
ACCOUNTS — Multi-Account Manager (adaptasi kebutuhan Panji: banyak akun & perangkat).
Setiap akun = 1 pasang API Key + Secret Binance (trade-only, IP-whitelist).
Disimpan di config/accounts.json (GITIGNORED — tidak pernah ke-push).
KEAMANAN:
  - Secret TIDAK pernah di-echo balik (hanya masked).
  - Tidak ada password akun Binance (tidak didukung exchange, tidak aman).
  - Live trading tetap butuh confirm_live_manually=false + restart (di settings).
"""
from __future__ import annotations
import os, json

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "accounts.json")


def load() -> dict:
    if not os.path.exists(PATH):
        return {"active": None, "accounts": []}
    try:
        return json.load(open(PATH))
    except Exception:
        return {"active": None, "accounts": []}


def save(db: dict):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(db, open(PATH, "w"), indent=2)


def add(name: str, mode: str, key: str, secret: str) -> dict:
    db = load()
    db["accounts"] = [a for a in db["accounts"]
                      if not (a["name"] == name and a["mode"] == mode)]
    db["accounts"].append({"name": name, "mode": mode, "key": key, "secret": secret})
    save(db)
    return db


def set_active(name: str) -> dict:
    db = load()
    if any(a["name"] == name for a in db["accounts"]):
        db["active"] = name
        save(db)
    return db


def delete(name: str) -> dict:
    db = load()
    db["accounts"] = [a for a in db["accounts"] if a["name"] != name]
    if db["active"] == name:
        db["active"] = None
    save(db)
    return db


def active_account() -> dict | None:
    db = load()
    if not db.get("active"):
        return None
    return next((a for a in db["accounts"] if a["name"] == db["active"]), None)


def masked(db: dict | None = None) -> dict:
    db = db or load()
    out = []
    for a in db.get("accounts", []):
        k = a.get("key", "")
        mask = (k[:4] + "*" * (len(k) - 8) + k[-4:]) if len(k) > 8 else "****"
        out.append({"name": a["name"], "mode": a["mode"], "key_masked": mask})
    return {"active": db.get("active"), "accounts": out}
