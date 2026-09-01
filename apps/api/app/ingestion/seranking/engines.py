from __future__ import annotations

ENGINE_LABELS: dict[str, str] = {
    "chatgpt": "ChatGPT",
    "google_ai_overview": "Google AI Overview",
    "google_ai_mode": "Google AI Mode",
    "perplexity": "Perplexity",
    "gemini": "Gemini",
}


def label_engine(base_name: str | None) -> str:
    if not base_name:
        return "Unknown"
    normalized = base_name.strip().lower()
    return ENGINE_LABELS.get(normalized, base_name.replace("_", " ").title())


def brand_mentioned(mention_position: int | None) -> bool | None:
    if mention_position is None:
        return None
    return mention_position > 0


def brand_cited(url_position: int | None) -> bool | None:
    if url_position is None:
        return None
    return url_position > 0
