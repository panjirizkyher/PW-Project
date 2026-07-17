"""
TELEGRAM NOTIFY — kirim briefing & alert ke chat Panji.
Gunakan requests (tanpa dependency berat). Token/chat_id dari env.
"""
from __future__ import annotations
import os
import requests


def send(message: str, settings: dict) -> bool:
    tg = settings.get("telegram", {})
    if not tg.get("enabled", False):
        return False
    token = os.environ.get(tg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
    chat_id = os.environ.get(tg.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message,
                                 "parse_mode": "Markdown"}, timeout=10)
        return True
    except Exception as e:
        print(f"[TELEGRAM] gagal: {e}")
        return False
