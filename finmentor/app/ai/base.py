"""LLM provider protocol. Providers only turn structured data into prose."""
from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def generate(self, prompt: str, system: str | None = None) -> str: ...
