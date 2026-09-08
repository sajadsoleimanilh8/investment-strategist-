"""
External API model layer — an *optional enhancement*, not a dependency.

If API_MODEL_PROVIDER=none (the default) or the provider is unreachable
(e.g. blocked in your region, no key set, request times out), every
function here returns None instead of raising, and the combiner layer
falls back to the local model alone. This is the fault-tolerance behavior
described in the project's architecture doc — never let the bot go down
just because one upstream provider is unavailable.
"""
from typing import Optional

import requests

from config import settings


def is_configured() -> bool:
    return settings.api_model_provider in {"openai", "anthropic"} and bool(settings.api_model_key)


def _call_openai(prompt: str) -> Optional[str]:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {settings.api_model_key}"}
    body = {
        "model": settings.api_model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=settings.api_timeout_seconds)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_anthropic(prompt: str) -> Optional[str]:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": settings.api_model_key,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": settings.api_model_name,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(url, headers=headers, json=body, timeout=settings.api_timeout_seconds)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def generate(prompt: str) -> Optional[str]:
    """Best-effort call to the configured external API. Returns None on any
    failure (not configured, blocked network, timeout, bad key) — callers
    must treat None as 'use the local model only', never as an error to
    surface to the end user."""
    if not is_configured():
        return None
    try:
        if settings.api_model_provider == "openai":
            return _call_openai(prompt)
        if settings.api_model_provider == "anthropic":
            return _call_anthropic(prompt)
    except Exception:
        return None
    return None
