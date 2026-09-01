from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def presence_from_statistics(payload: dict[str, Any]) -> tuple[float | None, float | None, int | None]:
    presence = payload.get("presence") if isinstance(payload.get("presence"), dict) else {}
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    return (
        _as_float(presence.get("mention_percent_in_top")),
        _as_float(presence.get("link_percent_in_top")),
        _as_int(stats.get("prompts_count")),
    )


def weighted_presence(
    rows: list[tuple[int, float | None, float | None]],
) -> tuple[float | None, float | None]:
    total_prompts = sum(prompts for prompts, _, _ in rows if prompts > 0)
    if total_prompts <= 0:
        return None, None

    mention_sum = 0.0
    mention_weight = 0
    link_sum = 0.0
    link_weight = 0
    for prompts, mention_pct, link_pct in rows:
        if prompts <= 0:
            continue
        if mention_pct is not None:
            mention_sum += mention_pct * prompts
            mention_weight += prompts
        if link_pct is not None:
            link_sum += link_pct * prompts
            link_weight += prompts

    mention = (mention_sum / mention_weight) if mention_weight else None
    link = (link_sum / link_weight) if link_weight else None
    return mention, link
