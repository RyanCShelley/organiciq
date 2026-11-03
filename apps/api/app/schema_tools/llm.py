"""The model side of the schema tools: one Claude call, and the two helpers that keep what comes back safe.

`extract_json` and `strip_breadcrumbs` are carried over from the Topic Hub tool unchanged (renamed without the underscore). The call
itself uses this app's own Claude client settings (see `app.ask.engine`) instead of the Anthropic SDK.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.ask.engine import DEPTHS, cost_usd
from app.core.settings import get_settings

TIMEOUT_SECONDS = 180.0


class ModelError(RuntimeError):
    pass


def call(depth: str, prompt: str, *, max_tokens: int = 3500) -> tuple[str, int, int]:
    """One Claude call for a prompt. Returns (text, input tokens, output tokens)."""
    key = get_settings().anthropic_api_key.strip()
    if not key:
        raise ModelError("The Anthropic key is not set on this install, so the model cannot be asked.")
    model = DEPTHS[depth][0]
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json={"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code >= 400:
        raise ModelError(f"The model did not answer ({response.status_code}).")
    body = response.json()
    usage = body.get("usage") or {}
    text = "".join(b.get("text", "") for b in body.get("content") or [] if b.get("type") == "text")
    return text, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)


def cost(depth: str, tokens_in: int, tokens_out: int) -> float:
    return float(cost_usd(depth, tokens_in, tokens_out))


def extract_json(text: str) -> dict[str, Any] | list[Any]:
    """Find the first JSON object/array in *text*, ignoring leading/trailing prose.

    Robust to three common LLM drifts:
      1. Trailing prose after the closing brace ("...} Let me know if...")
      2. Markdown fencing (``` ```json ... ``` ```)
      3. Leading prose ("Here is the audit: {...}")

    Uses :class:`json.JSONDecoder.raw_decode` which returns the parsed object
    plus an end-index, so anything after the first valid JSON value is
    ignored rather than raising ``Extra data``.
    """
    text = text.strip()
    if not text:
        raise ValueError("empty response")

    # Strip ```json / ``` markdown fences if present
    if text.startswith("```"):
        # Drop the opening fence (e.g. ```json\n or ```\n)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        # Drop a trailing closing fence if present
        closing = text.rfind("```")
        if closing != -1:
            text = text[:closing]
        text = text.strip()

    # Find the first `{` or `[` — tolerates leading prose
    start = -1
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start == -1:
        raise ValueError("no JSON object found in response")

    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(text[start:])
    if not isinstance(obj, (dict, list)):
        raise ValueError(
            f"top-level JSON value was {type(obj).__name__}, expected object or array"
        )
    return obj


def strip_breadcrumbs(
    parsed: dict[str, Any] | list[Any],
) -> tuple[dict[str, Any] | list[Any], list[str]]:
    """Remove any BreadcrumbList node or 'breadcrumb' property from the graph.

    Defence in depth: the prompt forbids breadcrumbs, but Claude can drift.
    """
    notes: list[str] = []

    def walk_nodes(nodes: list[Any]) -> list[Any]:
        kept: list[Any] = []
        for node in nodes:
            if not isinstance(node, dict):
                kept.append(node)
                continue
            t = node.get("@type", "")
            types = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
            if "BreadcrumbList" in types:
                notes.append(
                    f"Stripped BreadcrumbList node (id={node.get('@id', '?')}) "
                    "— breadcrumbs are excluded by project policy"
                )
                continue
            if "breadcrumb" in node:
                node.pop("breadcrumb", None)
                notes.append(
                    f"Stripped 'breadcrumb' property from {types or '?'} node"
                )
            kept.append(node)
        return kept

    if isinstance(parsed, list):
        return walk_nodes(parsed), notes
    if isinstance(parsed, dict):
        if "@graph" in parsed and isinstance(parsed["@graph"], list):
            parsed["@graph"] = walk_nodes(parsed["@graph"])
            return parsed, notes
        # Single root node
        if parsed.get("@type") == "BreadcrumbList":
            notes.append("Stripped root BreadcrumbList — excluded by project policy")
            return {}, notes
        if "breadcrumb" in parsed:
            parsed.pop("breadcrumb", None)
            notes.append("Stripped 'breadcrumb' property from root node")
        return parsed, notes
    return parsed, notes
