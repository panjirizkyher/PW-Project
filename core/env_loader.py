"""
ENV LOADER — parse config/.env ke os.environ (tanpa dependency ekstra).
Dipanggil di awal main.py / serve.py sebelum orchestrator dibuat.
"""
from __future__ import annotations
import os


def load_env(path: str = "config/.env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            # jangan timpa env yg sudah ada (mis. di-set shell)
            os.environ.setdefault(k, v)
