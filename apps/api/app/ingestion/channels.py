from __future__ import annotations

from app.models.config import ChannelRule, OrganicChannel


def classify_channel(
    source: str | None,
    medium: str | None,
    rules: list[ChannelRule],
) -> OrganicChannel:
    src = (source or "").strip().lower()
    med = (medium or "").strip().lower()

    # Direct / Unattributed is never auto-classified as Organic.
    if src in {"(direct)", "direct"} and med in {"(none)", "none", ""}:
        return OrganicChannel.DIRECT_UNATTRIBUTED

    for rule in sorted(rules, key=lambda r: r.priority):
        if not rule.active:
            continue
        host = (rule.match_host_contains or "").strip().lower()
        if host and host in src:
            return rule.channel

        match_source = (rule.match_source or "").strip().lower()
        match_medium = (rule.match_medium or "").strip().lower()
        if not match_source and not match_medium:
            continue
        source_ok = not match_source or match_source == src
        medium_ok = not match_medium or match_medium == med
        if source_ok and medium_ok:
            return rule.channel

    return OrganicChannel.OTHER
