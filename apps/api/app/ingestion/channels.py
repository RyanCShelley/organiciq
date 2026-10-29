from __future__ import annotations

from app.models.config import ChannelRule, OrganicChannel


def classify_channel(
    source: str | None,
    medium: str | None,
    rules: list[ChannelRule],
    default_channel_group: str | None = None,
) -> OrganicChannel:
    src = (source or "").strip().lower()
    med = (medium or "").strip().lower()

    # Direct / Unattributed is never auto-classified as Organic.
    if src in {"(direct)", "direct"} and med in {"(none)", "none", ""}:
        return OrganicChannel.DIRECT_UNATTRIBUTED

    ordered = sorted(rules, key=lambda r: r.priority)
    native = (default_channel_group or "").strip().lower()
    google_channels = {
        "ai assistant": OrganicChannel.AI_REFERRAL,
        "ai assistants": OrganicChannel.AI_REFERRAL,
        "organic search": OrganicChannel.ORGANIC_SEARCH,
        "direct": OrganicChannel.DIRECT_UNATTRIBUTED,
        "referral": OrganicChannel.REFERRAL,
        "paid search": OrganicChannel.PAID_SEARCH,
        "paid social": OrganicChannel.PAID_SOCIAL,
        "display": OrganicChannel.DISPLAY,
        "cross-network": OrganicChannel.CROSS_NETWORK,
        "paid shopping": OrganicChannel.OTHER_PAID,
        "paid video": OrganicChannel.OTHER_PAID,
        "paid other": OrganicChannel.OTHER_PAID,
        "audio": OrganicChannel.OTHER_PAID,
        "organic social": OrganicChannel.SOCIAL,
        "organic video": OrganicChannel.SOCIAL,
        "email": OrganicChannel.EMAIL,
    }
    # Preserve the legacy ChatGPT app host as an explicit AI source when a
    # native report is available; the provider domain is not the app referrer.
    if native and src in {"chat.openai.com", "chat.openai.com/"}:
        return OrganicChannel.AI_REFERRAL

    # Google distinguishes paid campaigns even when source/medium are missing.
    # The agency's explicit AI rules may identify AI referrals within Google's
    # broader channel; other rules remain fallbacks for unassigned sources.
    if native in google_channels:
        ai = classify_channel(source, medium, [r for r in ordered if r.channel == OrganicChannel.AI_REFERRAL])
        return ai if ai == OrganicChannel.AI_REFERRAL else google_channels[native]

    for rule in ordered:
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
