"""The model client's two invisible properties: reuse, and a ceiling.

Neither shows up in a single call, which is why both were absent.

`get_local_provider()` built a fresh `OllamaProvider` every time. That made the
30-second availability cache dead code — the TTL lived on the instance, so
nothing ever hit it — and opened a new connection per request to a server
usually running on the same machine.

And `generate` had no concurrency ceiling. `/ai/ask` is a synchronous route, so
each call holds one of Starlette's forty threadpool workers for the whole
generation; forty slow ones stall every other route in the process, including
`/healthz`, which fails the container healthcheck and restarts an API that was
merely busy.
"""
from __future__ import annotations

import threading

import pytest

from app.ai import local_llm
from app.ai.local_llm import LocalLLMUnavailable, OllamaProvider, get_local_provider
from app.core.config import settings


@pytest.fixture
def ollama_configured(monkeypatch):
    """Select the real provider without letting it reach a real server."""
    monkeypatch.setattr(settings, "local_llm_provider", "ollama")
    local_llm.reset_provider_cache()
    yield
    local_llm.reset_provider_cache()


# --- reuse ---------------------------------------------------------------

def test_the_provider_is_reused_between_calls(ollama_configured):
    """One object, so its caches and its connection survive the request."""
    assert get_local_provider() is get_local_provider()


def test_the_provider_keeps_one_http_session(ollama_configured):
    """A new connection per request to localhost is pure overhead."""
    provider = get_local_provider()

    assert provider._session is get_local_provider()._session


def test_the_availability_cache_can_actually_hit(ollama_configured, monkeypatch):
    """The point of memoising, stated as behaviour rather than identity.

    With a provider per call the TTL was unreachable: every request built an
    instance whose cache had never been populated, so every request re-probed
    `/api/tags`.
    """
    probes = {"n": 0}

    class _Response:
        @staticmethod
        def raise_for_status() -> None: ...

        @staticmethod
        def json() -> dict:
            return {"models": [{"name": settings.local_llm_model}]}

    def counting_get(url, **kwargs):
        probes["n"] += 1
        return _Response()

    monkeypatch.setattr(get_local_provider()._session, "get", counting_get)

    for _ in range(5):
        assert get_local_provider().available() is True

    assert probes["n"] == 1, f"probed the server {probes['n']} times for 5 checks"


def test_the_fake_provider_is_still_built_per_call(monkeypatch):
    """Tests flip a class-level switch on it, so it must not be memoised."""
    monkeypatch.setattr(settings, "local_llm_provider", "fake")

    assert get_local_provider() is not get_local_provider()


# --- the concurrency ceiling ---------------------------------------------

def _generation_that_blocks(started: threading.Event, release: threading.Event):
    """A `post` that parks until released, so slots stay occupied."""
    def blocking_post(url, **kwargs):
        started.set()
        release.wait(timeout=5)
        raise AssertionError("released without being cancelled")
    return blocking_post


def test_a_generation_past_the_ceiling_is_refused_not_queued(monkeypatch):
    """Refused immediately, so the caller's worker is not held hostage.

    Queueing is what the ceiling exists to prevent: waiting for a slot holds
    a threadpool worker for the length of somebody else's generation, which
    is the stall this is meant to stop.
    """
    monkeypatch.setattr(settings, "local_llm_max_concurrency", 1)
    provider = OllamaProvider()

    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(provider._session, "post",
                        _generation_that_blocks(started, release))

    holder = threading.Thread(target=lambda: _swallow(provider), daemon=True)
    holder.start()
    assert started.wait(timeout=2), "the first generation never started"

    try:
        with pytest.raises(LocalLLMUnavailable, match="in flight"):
            OllamaProvider().generate("second question")
    finally:
        release.set()
        holder.join(timeout=2)


def test_the_ceiling_releases_when_a_generation_finishes(monkeypatch):
    """A slot that is never given back is a ceiling that becomes a wall."""
    monkeypatch.setattr(settings, "local_llm_max_concurrency", 1)
    provider = OllamaProvider()

    monkeypatch.setattr(provider._session, "post",
                        lambda url, **kwargs: (_ for _ in ()).throw(OSError("down")))

    for _ in range(3):
        with pytest.raises(LocalLLMUnavailable):
            provider.generate("a question")

    assert local_llm._gate.in_flight == 0, "a slot leaked"


def test_a_ceiling_of_zero_disables_it(monkeypatch):
    """The escape hatch, for a deployment that wants the old behaviour."""
    monkeypatch.setattr(settings, "local_llm_max_concurrency", 0)
    provider = OllamaProvider()
    monkeypatch.setattr(provider._session, "post",
                        lambda url, **kwargs: (_ for _ in ()).throw(OSError("down")))

    # Refused for being down, not for being over a ceiling.
    with pytest.raises(LocalLLMUnavailable, match="down"):
        provider.generate("a question")


def test_the_timeout_is_configurable_and_no_longer_a_minute(monkeypatch):
    """Sixty seconds per worker was the whole problem."""
    seen = {}

    provider = OllamaProvider()
    monkeypatch.setattr(settings, "local_llm_max_concurrency", 4)

    def capturing_post(url, **kwargs):
        seen.update(kwargs)
        raise OSError("down")

    monkeypatch.setattr(provider._session, "post", capturing_post)
    with pytest.raises(LocalLLMUnavailable):
        provider.generate("a question")

    assert seen["timeout"] == settings.local_llm_timeout_seconds
    assert settings.local_llm_timeout_seconds <= 30


def _swallow(provider) -> None:
    try:
        provider.generate("first question")
    except BaseException:                    # the thread is a fixture, not the test
        pass
