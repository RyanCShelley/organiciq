"""The four AI platforms a run asks. Plain HTTPS calls, no vendor SDKs.

Models and prices follow the llmviz tool this was ported from. A platform without an API key on this
install is skipped, never failed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from app.core.settings import get_settings

PLATFORMS = ("openai", "perplexity", "gemini", "anthropic")
DISPLAY = {"openai": "ChatGPT", "perplexity": "Perplexity", "gemini": "Gemini", "anthropic": "Claude"}
MODELS = {
    "openai": "gpt-4o-mini",
    "perplexity": "sonar",
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-haiku-4-5-20251001",
}
MAX_TOKENS = 1024
TEMPERATURE = 0.3
TIMEOUT_SECONDS = 90.0
RETRIES = 3

#: Dollars per 1,000 tokens (input, output).
RATES = {
    "openai": (0.00015, 0.0006),
    "perplexity": (0.0002, 0.0002),
    "gemini": (0.000075, 0.0003),
    "anthropic": (0.001, 0.005),
}

SYSTEM = (
    "You are a helpful search assistant. When answering, cite specific companies, websites, and sources "
    "when relevant. Include URLs when you can."
)
PERPLEXITY_SYSTEM = "You are a helpful search assistant. Provide detailed answers with sources."


@dataclass
class PlatformAnswer:
    text: str
    citations: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class PlatformError(Exception):
    """The platform answered with an error, or did not answer."""


def api_key(platform: str) -> str:
    settings = get_settings()
    return {
        "openai": settings.openai_api_key,
        "perplexity": settings.perplexity_api_key,
        "gemini": settings.gemini_api_key,
        "anthropic": settings.anthropic_api_key,
    }[platform].strip()


def enabled_platforms() -> list[str]:
    return [p for p in PLATFORMS if api_key(p)]


def cost_usd(platform: str, input_tokens: int, output_tokens: int) -> float:
    rate_in, rate_out = RATES[platform]
    return round(input_tokens / 1000 * rate_in + output_tokens / 1000 * rate_out, 6)


def _post(url: str, *, headers: dict[str, str], body: dict[str, Any], label: str) -> dict[str, Any]:
    """POST with a few retries on throttling and server errors."""
    last = ""
    for attempt in range(RETRIES):
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            last = f"{label}: {exc}"
        else:
            if response.status_code < 400:
                return response.json()
            detail = response.text[:300]
            last = f"{label} {response.status_code}: {detail}"
            if response.status_code not in (408, 429) and response.status_code < 500:
                break
        time.sleep(1.5 * (attempt + 1))
    raise PlatformError(last)


def _openai(prompt: str, key: str) -> PlatformAnswer:
    raw = _post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        body={
            "model": MODELS["openai"],
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        },
        label="OpenAI",
    )
    usage = raw.get("usage") or {}
    choices = raw.get("choices") or [{}]
    return PlatformAnswer(
        text=(choices[0].get("message") or {}).get("content") or "",
        input_tokens=usage.get("prompt_tokens") or 0,
        output_tokens=usage.get("completion_tokens") or 0,
    )


def _perplexity(prompt: str, key: str) -> PlatformAnswer:
    raw = _post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        body={
            "model": MODELS["perplexity"],
            "messages": [{"role": "system", "content": PERPLEXITY_SYSTEM}, {"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        },
        label="Perplexity",
    )
    usage = raw.get("usage") or {}
    choices = raw.get("choices") or [{}]
    citations = raw.get("citations")
    return PlatformAnswer(
        text=(choices[0].get("message") or {}).get("content") or "",
        citations=[c for c in citations if isinstance(c, str)] if isinstance(citations, list) else [],
        input_tokens=usage.get("prompt_tokens") or 0,
        output_tokens=usage.get("completion_tokens") or 0,
    )


def _gemini(prompt: str, key: str) -> PlatformAnswer:
    raw = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODELS['gemini']}:generateContent",
        headers={"x-goog-api-key": key},
        body={
            "contents": [{"parts": [{"text": f"{SYSTEM}\n\n{prompt}"}]}],
            # Gemini 2.5 spends its output allowance on hidden "thinking" first; left on, the visible answer is cut off
            # after a couple of hundred characters. A plain answer needs no thinking.
            "generationConfig": {
                "maxOutputTokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        },
        label="Gemini",
    )
    usage = raw.get("usageMetadata") or {}
    parts = (((raw.get("candidates") or [{}])[0].get("content")) or {}).get("parts") or []
    return PlatformAnswer(
        text="".join(p.get("text", "") for p in parts),
        input_tokens=usage.get("promptTokenCount") or 0,
        output_tokens=usage.get("candidatesTokenCount") or 0,
    )


def _anthropic(prompt: str, key: str) -> PlatformAnswer:
    raw = _post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        body={
            "model": MODELS["anthropic"],
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": f"{SYSTEM}\n\n{prompt}"}],
        },
        label="Anthropic",
    )
    usage = raw.get("usage") or {}
    return PlatformAnswer(
        text="".join(b.get("text", "") for b in raw.get("content") or [] if b.get("type") == "text"),
        input_tokens=usage.get("input_tokens") or 0,
        output_tokens=usage.get("output_tokens") or 0,
    )


_CALLS: dict[str, Callable[[str, str], PlatformAnswer]] = {
    "openai": _openai,
    "perplexity": _perplexity,
    "gemini": _gemini,
    "anthropic": _anthropic,
}


def ask(platform: str, prompt: str) -> PlatformAnswer:
    key = api_key(platform)
    if not key:
        raise PlatformError(f"No API key for {DISPLAY[platform]} on this install")
    return _CALLS[platform](prompt, key)
