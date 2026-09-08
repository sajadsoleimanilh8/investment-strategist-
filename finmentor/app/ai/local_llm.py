"""Local LLM adapter (Ollama by default). The reliable core — no API key,
no external network. Ported from legacy ai/local_model.py.
"""
from __future__ import annotations

import requests

from app.ai.prompts import SYSTEM_PROMPT
from app.core.config import settings


class LocalLLMUnavailable(Exception):
    pass


class OllamaProvider:
    name = "ollama"

    def available(self) -> bool:
        try:
            requests.get(f"{settings.ollama_host}/api/tags", timeout=2).raise_for_status()
            return True
        except Exception:
            return False

    def generate(self, prompt: str, system: str | None = None) -> str:
        full = f"{system or SYSTEM_PROMPT}\n\nUser: {prompt}\nAssistant:"
        try:
            resp = requests.post(
                f"{settings.ollama_host}/api/generate",
                json={"model": settings.local_llm_model, "prompt": full, "stream": False},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as exc:  # noqa: BLE001
            raise LocalLLMUnavailable(str(exc)) from exc


def get_local_provider() -> OllamaProvider:
    # TODO(phase-5): switch on settings.local_llm_provider when more than Ollama exists.
    return OllamaProvider()
