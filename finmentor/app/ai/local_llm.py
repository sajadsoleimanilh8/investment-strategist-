"""Local LLM adapter (Ollama by default). The reliable core — no API key,
no external network beyond the machine the model runs on.

`FakeLocalProvider` is the test double: deterministic, offline, and it echoes
part of the context it was handed, so a pipeline test can prove the context
actually reached the model. `LOCAL_LLM_PROVIDER=fake` selects it — tests never
touch a live model.

Two properties of the Ollama provider are worth stating here, because both
were absent and neither is visible from a single call.

**One provider, reused.** `get_local_provider()` used to construct a fresh
`OllamaProvider` every call, which made its availability cache dead code — the
TTL was per instance, so nothing ever hit it — and opened a new TCP connection
per request to a server that is usually on the same machine. The provider is
now memoised and holds a `requests.Session`.

**A ceiling on concurrent generations.** `/ai/ask` is a synchronous route and
occupies a threadpool worker for the whole generation. Without a ceiling,
enough slow calls stall every other route in the process, `/healthz` included,
which turns a busy API into a restarting one. Ollama serialises requests
internally, so queueing past the ceiling bought latency rather than
throughput; past it the caller is refused quickly and drops to the
deterministic tier, which is a plainer answer rather than no answer.
"""
from __future__ import annotations

import json
import re
import threading
import time
from contextlib import contextmanager
from functools import lru_cache

import requests

from app.ai.prompts import SYSTEM_PROMPT
from app.core.config import settings

#: how long an `available()` result is trusted before re-checking the server
AVAILABILITY_TTL_SECONDS = 30.0


class _Gate:
    """A ceiling on concurrent generations that never blocks.

    `slot` either takes one or says no immediately. Waiting would reintroduce
    exactly what the ceiling exists to prevent: a worker held for the length
    of somebody else's generation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight = 0

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @contextmanager
    def slot(self, limit: int):
        if limit <= 0:                       # disabled
            yield True
            return
        with self._lock:
            taken = self._in_flight < limit
            if taken:
                self._in_flight += 1
        try:
            yield taken
        finally:
            if taken:
                with self._lock:
                    self._in_flight -= 1


#: Module-level: the ceiling belongs to the process talking to one model
#: server, not to any single provider object.
_gate = _Gate()


class LocalLLMUnavailable(Exception):
    """The local model could not answer — caller must fall back, never crash."""


class OllamaProvider:
    """Talks to Ollama's /api/chat. Any failure becomes `LocalLLMUnavailable`."""

    name = "ollama"

    def __init__(self) -> None:
        self._available_until = 0.0
        self._available = False
        # Kept alive between calls. Ollama usually runs on this machine, so a
        # fresh connection per request is pure overhead on a hot path.
        self._session = requests.Session()

    def available(self) -> bool:
        """True only if the server answers AND the configured model is installed.

        A running server with no model pulled would otherwise look healthy and
        then fail on the first real request. Cached briefly so a burst of
        requests does not re-probe every time.
        """
        now = time.monotonic()
        if now < self._available_until:
            return self._available

        try:
            response = self._session.get(f"{settings.ollama_host}/api/tags", timeout=2)
            response.raise_for_status()
            installed = {model.get("name", "") for model in response.json().get("models", [])}
            wanted = settings.local_llm_model
            # Ollama reports "llama3.2:3b"; accept a bare name without its tag too
            self._available = any(
                name == wanted or name.split(":")[0] == wanted.split(":")[0]
                for name in installed
            )
        except Exception:  # noqa: BLE001 - unreachable, bad JSON, timeout: all "no"
            self._available = False

        self._available_until = now + AVAILABILITY_TTL_SECONDS
        return self._available

    def generate(self, prompt: str, system: str | None = None) -> str:
        with _gate.slot(settings.local_llm_max_concurrency) as taken:
            if not taken:
                # Refused rather than queued. `LocalLLMUnavailable` is the
                # signal the whole AI layer already handles: the caller drops
                # to the deterministic tier and the user gets their verified
                # figures instead of waiting behind a saturated model.
                raise LocalLLMUnavailable(
                    f"{settings.local_llm_max_concurrency} generations already "
                    "in flight"
                )
            try:
                response = self._session.post(
                    f"{settings.ollama_host}/api/chat",
                    json={
                        "model": settings.local_llm_model,
                        "messages": [
                            {"role": "system", "content": system or SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "options": {
                            "temperature": settings.local_llm_temperature,
                            "num_predict": settings.ai_max_tokens,
                        },
                    },
                    timeout=settings.local_llm_timeout_seconds,
                )
                response.raise_for_status()
                text = response.json()["message"]["content"].strip()
            except LocalLLMUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001
                raise LocalLLMUnavailable(str(exc)) from exc

        if not text:
            raise LocalLLMUnavailable("the model returned an empty response")
        return text


class FakeLocalProvider:
    """Deterministic stand-in for tests and offline demos.

    It writes a sentence or two that quotes figures out of the prompt's context
    block, so a test asserting "the context reached the model" is meaningful,
    and every number it emits is grounded by construction — the safety layer
    sees a realistic, well-behaved draft.

    Set `FakeLocalProvider.unavailable = True` (or construct with
    `unavailable=True`) to exercise the local-model-down tier.
    """

    name = "fake"

    #: class-level switch so a test can knock the local tier over globally
    unavailable = False

    def __init__(self, *, unavailable: bool | None = None) -> None:
        self._unavailable = unavailable

    def _is_down(self) -> bool:
        return self._unavailable if self._unavailable is not None else type(self).unavailable

    def available(self) -> bool:
        return not self._is_down()

    def generate(self, prompt: str, system: str | None = None) -> str:
        if self._is_down():
            raise LocalLLMUnavailable("fake provider is switched off")

        context = _context_block(prompt)
        if context.get("unavailable"):
            return (
                f"I do not have that information: {context['unavailable']} "
                "Add it and ask me again."
            )

        figures = ", ".join(f"{key} is {value}" for key, value in _leaf_figures(context)[:3])
        merged = "Merging both drafts. " if "Draft A" in prompt else ""
        if not figures:
            return f"{merged}Here is what your numbers show."
        return f"{merged}Here is what your numbers show: {figures}."


def _context_block(prompt: str) -> dict:
    """Pull the JSON context back out of a rendered prompt template."""
    match = re.search(r"\{.*\}", prompt, re.DOTALL)
    if match is None:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _leaf_figures(context: dict, prefix: str = "") -> list[tuple[str, object]]:
    """Flatten a context to (name, scalar) pairs the fake answer can quote."""
    figures: list[tuple[str, object]] = []
    for key, value in context.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            figures.extend(_leaf_figures(value, prefix=f"{name}."))
        elif isinstance(value, (int, float, str)) and not isinstance(value, bool):
            figures.append((name, value))
    return figures


@lru_cache(maxsize=1)
def _ollama() -> OllamaProvider:
    """The one Ollama provider for this process.

    Memoised so its availability cache and its HTTP session survive between
    requests. A fresh instance per call made both useless: the 30-second TTL
    was per object, so it never once prevented a re-probe.
    """
    return OllamaProvider()


def reset_provider_cache() -> None:
    """Drop the memoised provider. For tests that switch configuration."""
    _ollama.cache_clear()


def get_local_provider():
    """The configured local provider. `fake` keeps tests off a live model.

    The fake is built per call on purpose: it is stateless apart from a
    deliberate class-level switch, and tests construct it directly to
    exercise the model-down tier.
    """
    if settings.local_llm_provider == "fake":
        return FakeLocalProvider()
    return _ollama()
