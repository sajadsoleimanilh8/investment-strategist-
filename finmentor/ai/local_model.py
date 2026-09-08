"""
Local model layer — talks to Ollama (https://ollama.com) running on the same
machine. This is the *reliable core*: no API key, no external network
dependency, works even when foreign APIs are unreachable.

Setup:
    1) install Ollama
    2) ollama pull llama3.2:3b   (or phi3:mini / mistral, see README)
    3) ollama serve              (usually starts automatically)
"""
import requests

from config import settings

SYSTEM_PROMPT = (
    "You are a financial-education assistant. You explain market data and "
    "personal-finance concepts in clear, simple language. You NEVER promise "
    "returns, NEVER tell the user to buy/sell a specific asset, and you always "
    "frame market commentary as 'recent trend' not a prediction. Answer in the "
    "same language the user wrote in."
)


class LocalModelUnavailable(Exception):
    pass


def generate(prompt: str, system_prompt: str = SYSTEM_PROMPT, timeout: float = 15.0) -> str:
    """Call the local Ollama model. Raises LocalModelUnavailable if the
    Ollama server isn't running so callers can decide how to degrade."""
    url = f"{settings.ollama_host}/api/generate"
    full_prompt = f"{system_prompt}\n\nUser: {prompt}\nAssistant:"
    try:
        resp = requests.post(
            url,
            json={"model": settings.ollama_model, "prompt": full_prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as exc:
        raise LocalModelUnavailable(f"Ollama not reachable at {settings.ollama_host}: {exc}") from exc


def generate_safe(prompt: str, fallback: str = None) -> str:
    """Same as generate(), but never raises — returns `fallback` (or a
    canned message) instead. Handy for the bot handlers."""
    try:
        return generate(prompt)
    except LocalModelUnavailable:
        return fallback or (
            "مدل محلی در دسترس نیست. مطمئن شو Ollama رو نصب و اجرا کردی "
            "(راهنما در README)."
        )
