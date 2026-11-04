"""The model behind one interface.

Speaks the OpenAI-compatible chat protocol with tool calling, which is what
vLLM, Together, Fireworks, Modal and Ollama all serve. Stock Qwen and a
fine-tuned LoRA of it are the same call with a different model name.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.core.settings import get_settings


class GatewayError(RuntimeError):
    """The model could not be reached or answered with something unusable."""


class GatewayNotConfigured(GatewayError):
    """LLM_BASE_URL is not set."""


class Gateway(Protocol):
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """One model turn. Returns the assistant message: `content` and,
        when the model wants tools, `tool_calls`."""
        ...


class OpenAICompatGateway:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            # Low: this answers questions about numbers.
            "temperature": 0.2,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise GatewayError(f"model call failed: {exc}") from exc


def get_gateway() -> Gateway:
    settings = get_settings()
    if not settings.llm_base_url:
        raise GatewayNotConfigured("LLM_BASE_URL is not set")
    return OpenAICompatGateway(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
    )
