"""
ONCHAIN / SENTIMENT — Fear & Greed Index (crypto).
Sumber publik: alternative.me API. Nakamoto X memakai ini.
"""
from __future__ import annotations
import urllib.request
import json
from typing import Optional


def fear_greed() -> dict:
    """Return dict: {value, classification} atau {} bila gagal."""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        d = data["data"][0]
        return {"value": int(d["value"]), "classification": d["value_classification"]}
    except Exception as e:
        return {"error": str(e)}
