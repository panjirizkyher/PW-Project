"""
LLM Persona Layer — PEWE Trading Desk
OpenAI-compatible client. Used by agent personas for natural-language analysis.
Falls back gracefully if disabled or no key.
"""
from __future__ import annotations
import os
from typing import Optional

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


class LLMClient:
    def __init__(self, settings: dict):
        self.cfg = settings.get("llm", {})
        self.enabled = bool(self.cfg.get("enabled", False))
        self.base_url = self.cfg.get("base_url", "https://inference.nousresearch.com/v1")
        self.model = self.cfg.get("model", "tencent/hy3:free")
        self.temperature = float(self.cfg.get("temperature", 0.3))
        self.api_key = os.environ.get(self.cfg.get("api_key_env", "LLM_API_KEY"), "")
        self._client = None
        if self.enabled and OpenAI and self.api_key:
            try:
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except Exception as e:  # pragma: no cover
                print(f"[LLM] init gagal: {e}. Persona akan pakai teks statis.")
                self._client = None

    def ask(self, system_prompt: str, user_prompt: str, max_tokens: int = 400) -> str:
        """Return LLM response, or a static fallback if disabled/unavailable."""
        if not (self.enabled and self._client):
            return "(LLM nonaktif — teks analisis statis. Aktifkan di settings.yaml + isi API key.)"
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"(LLM error: {e})"
