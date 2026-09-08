"""Optional remote LLM adapter. Returns None on ANY failure so the caller
falls back to local. Ported from legacy ai/api_model.py.
"""
from __future__ import annotations

import requests

from app.core.config import settings


def is_enabled() -> bool:
    return (
        settings.remote_llm_enabled
        and settings.remote_llm_provider in {"openai", "anthropic"}
        and bool(settings.remote_llm_api_key)
    )


def generate(prompt: str) -> str | None:
    if not is_enabled():
        return None
    try:
        if settings.remote_llm_provider == "openai":
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.remote_llm_api_key}"},
                json={"model": settings.remote_llm_model,
                      "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.4},
                timeout=settings.remote_llm_timeout_seconds,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        if settings.remote_llm_provider == "anthropic":
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.remote_llm_api_key,
                         "anthropic-version": "2023-06-01"},
                json={"model": settings.remote_llm_model, "max_tokens": 512,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=settings.remote_llm_timeout_seconds,
            )
            r.raise_for_status()
            return r.json()["content"][0]["text"].strip()
    except Exception:  # noqa: BLE001
        return None
    return None
