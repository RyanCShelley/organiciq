"""Anchor-text generation for inlink recommendations.

Follows Google's own anchor-text guidance: descriptive, concise, varied.
For each (source, target) pair we produce a ranked list of candidate
anchors across four types — partial match, branded, generic, and naked
URL — and pick a primary recommendation that isn't already heavily used
on the source domain.

No LLM calls. Everything is derived from data we already have: the
target page's title/URL/keywords + cluster keywords, plus a running
tally of how often each anchor-type has been "used up" so we vary
across suggestions for the same source.

Reference: Google's guidance on anchors (be descriptive, concise, don't
over-optimize, vary naturally).
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Iterable

# Generic "read more" style anchors we rotate through to avoid robotic
# repetition. Ordered from most to least useful.
_GENERIC_POOL: tuple[str, ...] = (
    "this guide",
    "our walkthrough",
    "related coverage",
    "the full breakdown",
    "this resource",
    "our write-up",
)

# Common stopwords that we strip when shortening a title into a partial-match.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "of", "for", "to", "in", "on",
        "at", "by", "with", "from", "as", "is", "are", "was", "were", "be",
        "been", "being", "do", "does", "did", "have", "has", "had", "this",
        "that", "these", "those", "it", "its", "your", "you", "how", "what",
        "why", "best", "top", "complete", "ultimate", "guide", "guides",
        "blog", "post", "article", "2024", "2025", "2026",
        "should", "must", "need", "can", "will", "using", "used", "right",
        "now", "today", "get", "make", "makes", "making",
    }
)

# Acronyms that should be preserved in uppercase inside any anchor text.
_PRESERVE_CASE: frozenset[str] = frozenset(
    {
        "AI", "SEO", "SEM", "PPC", "SERP", "SERPs", "CTR", "CRO", "CMS",
        "API", "APIs", "UI", "UX", "URL", "URLs", "SaaS", "B2B", "B2C",
        "RV", "ROI", "KPI", "KPIs", "HTML", "CSS", "JS", "PDF", "FAQ",
        "GEO", "LLM", "LLMs", "NLP", "SMS", "MMS", "AR", "VR", "IoT",
    }
)

# Words we never want as a standalone anchor — too generic to describe
# anything specific.
_TOO_GENERIC_SOLO: frozenset[str] = frozenset(
    {"click", "here", "more", "read", "learn", "see"}
)


def _strip_site_suffix(title: str) -> str:
    """Remove trailing ' - Brand' / ' | Brand' from a title."""
    for sep in (" - ", " | ", " — ", " – "):
        if sep in title:
            head, _, _ = title.rpartition(sep)
            if len(head.split()) >= 2:
                return head.strip()
    return title.strip()


def _slug_words(url: str) -> list[str]:
    """Pull meaningful words out of the URL path."""
    path = urllib.parse.urlparse(url).path
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    parts = re.split(r"[-_]+", slug)
    return [p for p in parts if p and not p.isdigit()]


def _clean_words(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text)
    return [t for t in tokens if t.lower() not in _STOPWORDS]


def _title_case(phrase: str) -> str:
    """Title-case a phrase, preserving acronyms (AI, SEO, …) and mid-phrase stopwords."""
    acronym_upper = {a.upper(): a for a in _PRESERVE_CASE}
    words = phrase.split()
    if not words:
        return phrase
    out: list[str] = []
    for i, w in enumerate(words):
        stripped = re.sub(r"[^A-Za-z0-9]", "", w)
        if stripped.upper() in acronym_upper:
            # Preserve the canonical casing of the acronym.
            preserved = acronym_upper[stripped.upper()]
            out.append(w.replace(stripped, preserved))
            continue
        if i > 0 and w.lower() in _STOPWORDS:
            out.append(w.lower())
        else:
            out.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    return " ".join(out)


def _shorten_to_anchor(text: str, max_words: int = 6) -> str:
    """Shorten a title to a concise anchor phrase, preserving core keywords."""
    cleaned = _strip_site_suffix(text)
    # Drop leading "How to" / "What is" so the anchor reads naturally mid-sentence.
    for lead in ("how to ", "what is ", "what are ", "why ", "the "):
        if cleaned.lower().startswith(lead):
            cleaned = cleaned[len(lead):]
            break
    # Drop parentheticals up front, then cap length.
    words = [w for w in cleaned.split() if not w.startswith("(") and not w.endswith(")")]
    if len(words) > max_words:
        words = words[:max_words]
    # Strip trailing stopwords — "AI Search Visibility Tools You Should" → "AI Search Visibility Tools".
    while words and words[-1].lower() in _STOPWORDS:
        words.pop()
    # Strip leading stopwords too for good measure.
    while words and words[0].lower() in _STOPWORDS:
        words.pop(0)
    return " ".join(words).strip(" ,.:;-—–")


def _detect_brand(url: str) -> str | None:
    """Derive a human brand name from the hostname.

    We don't try to be clever about compound brands ("mattressinsider" →
    "Mattress Insider") because it can mis-split. We pass through the
    raw label title-cased; if the user wants a friendlier brand they can
    override it in the project name later.
    """
    host = urllib.parse.urlparse(url).netloc.lower()
    host = re.sub(r"^www\.", "", host)
    if not host:
        return None
    label = host.split(".")[0]
    # If the label has explicit separators, use them.
    if "-" in label or "_" in label:
        parts = re.split(r"[-_]+", label)
        return " ".join(_title_case(p) for p in parts if p)
    # Short all-letter labels (<=4 chars) are usually acronyms — uppercase them.
    if label.isalpha() and len(label) <= 4:
        return label.upper()
    return _title_case(label)


def _is_too_generic(phrase: str) -> bool:
    toks = phrase.lower().split()
    if len(toks) == 1 and toks[0] in _TOO_GENERIC_SOLO:
        return True
    if not toks:
        return True
    return all(t in _STOPWORDS for t in toks)


def build_candidates(
    target_url: str,
    target_title: str | None,
    cluster_keywords: Iterable[str] = (),
    hub_label: str | None = None,
    matched_seed: str | None = None,
) -> dict[str, list[str]]:
    """Return candidate anchors grouped by type.

    Types:
      - partial_match: short descriptive phrase derived from the title/slug
      - branded: the site/brand name (used sparingly)
      - generic: "this guide" / "our walkthrough" (used to maintain variety)
      - naked_url: the URL itself
    """
    partial: list[str] = []

    # 1. Shortened title (primary partial match).
    if target_title:
        short = _shorten_to_anchor(target_title, max_words=6)
        if short and not _is_too_generic(short):
            partial.append(short.lower())

    # 2. Seed / hub label as partial match (pulls in the canonical topic term).
    if matched_seed:
        partial.append(matched_seed.lower())
    elif hub_label:
        # Only use generic hub labels like "SEO" / "PPC"; skip things like "Orphan".
        if hub_label.lower() not in {"orphan", "uncategorized"}:
            partial.append(hub_label.lower())

    # 3. Slug-derived phrase as a fallback partial match.
    slug_parts = _slug_words(target_url)
    if slug_parts:
        slug_phrase = " ".join(slug_parts[:5])
        cleaned_slug = " ".join(w for w in slug_phrase.split() if w.lower() not in _STOPWORDS)
        if cleaned_slug and not _is_too_generic(cleaned_slug):
            partial.append(cleaned_slug.lower())

    # 4. Cluster keywords combined — gives a "topic + context" anchor.
    #    Pick the first 2 keywords that are not already in the partials.
    joined_so_far = " ".join(partial)
    extra_kw: list[str] = []
    for kw in cluster_keywords:
        k = kw.strip()
        if not k or k.lower() in joined_so_far:
            continue
        extra_kw.append(k)
        if len(extra_kw) == 2:
            break
    if extra_kw:
        partial.append(" ".join(extra_kw).lower())

    # Dedup + de-generify while preserving order.
    seen: set[str] = set()
    partial_unique: list[str] = []
    for p in partial:
        norm = re.sub(r"\s+", " ", p).strip(" ,.:;-—–'\"")
        if not norm or norm in seen or _is_too_generic(norm):
            continue
        seen.add(norm)
        partial_unique.append(norm)

    branded: list[str] = []
    brand = _detect_brand(target_url)
    if brand:
        # Prefer "Brand's Partial Match" over naked brand.
        if partial_unique:
            branded.append(f"{brand}'s {_title_case(partial_unique[0])}")
        branded.append(brand)

    generic = list(_GENERIC_POOL)

    naked_url = [target_url]

    return {
        "partial_match": [_title_case(p) for p in partial_unique],
        "branded": branded,
        "generic": generic,
        "naked_url": naked_url,
    }


def pick_primary(
    candidates: dict[str, list[str]],
    used_on_source: dict[str, int],
    slot_on_target: int = 0,
) -> tuple[str, str]:
    """Pick the best candidate anchor, varying across both target slot + source usage.

    Strategy — Google's "vary naturally" rule:
      - slot 0: prefer the richest partial match (most informative primary).
      - slot 1: branded variant ("Brand's Partial").
      - slot 2: alternate partial match (topic keyword or hub).
      - slot 3: generic ("this guide").
      - slot 4: another partial.
      - slot 5: naked URL (rarely).
      - slot 6+: cycle back to another partial / generic.
      - Never repeat the same exact anchor twice on the same source domain.
    """
    partial = candidates.get("partial_match") or []
    branded = candidates.get("branded") or []
    generic = candidates.get("generic") or []
    naked = candidates.get("naked_url") or []

    # Slot-specific preferred ordering for the primary pick.
    slot = slot_on_target % 7
    if slot == 0:
        preferred = [partial, branded, generic, naked]
    elif slot == 1:
        preferred = [branded, partial, generic, naked]
    elif slot == 2:
        preferred = [partial[1:] + partial[:1], branded, generic, naked]
    elif slot == 3:
        preferred = [generic, partial, branded, naked]
    elif slot == 4:
        preferred = [partial[2:] + partial[:2], branded, generic, naked]
    elif slot == 5 and naked:
        preferred = [naked, partial, generic, branded]
    else:
        preferred = [generic, partial, branded, naked]

    for group in preferred:
        for anchor in group:
            if used_on_source.get(anchor, 0) == 0:
                used_on_source[anchor] = 1
                return anchor, _group_name_for(anchor, candidates)

    # Fallback — every candidate already used on this source. Pick the least-used.
    all_anchors = [
        (a, used_on_source.get(a, 0), _group_name_for(a, candidates))
        for group in preferred for a in group
    ]
    if not all_anchors:
        return "", "generic"
    all_anchors.sort(key=lambda x: x[1])
    anchor, _, kind = all_anchors[0]
    used_on_source[anchor] = used_on_source.get(anchor, 0) + 1
    return anchor, kind


def _group_name_for(anchor: str, candidates: dict[str, list[str]]) -> str:
    for name, group in candidates.items():
        if anchor in group:
            return name
    return "generic"


def annotate_suggestions(
    recommendations: list[dict[str, Any]],
    cluster_keywords_by_hub: dict[str, list[str]] | None = None,
    seed_by_hub: dict[str, str] | None = None,
) -> None:
    """Mutate recommendations in place to add anchor candidates + primary pick.

    For each target page we build one set of candidates, then pick a primary
    anchor per (source, target) pair, rotating types so the source page
    doesn't end up linking out with the same phrase every time.
    """
    cluster_keywords_by_hub = cluster_keywords_by_hub or {}
    seed_by_hub = seed_by_hub or {}
    used_by_source: dict[str, dict[str, int]] = {}

    for rec in recommendations:
        target_url = rec["target_url"]
        target_title = rec.get("target_title")
        hub_label = rec.get("target_hub")
        candidates = build_candidates(
            target_url=target_url,
            target_title=target_title,
            cluster_keywords=cluster_keywords_by_hub.get(hub_label or "", []),
            hub_label=hub_label,
            matched_seed=seed_by_hub.get(hub_label or ""),
        )
        rec["anchor_candidates"] = candidates

        for slot, suggestion in enumerate(rec.get("suggestions", [])):
            source_url = suggestion["source_url"]
            used = used_by_source.setdefault(source_url, {})
            primary, kind = pick_primary(candidates, used, slot_on_target=slot)
            suggestion["suggested_anchor"] = primary
            suggestion["anchor_type"] = kind
            # Secondary anchors: two alternates of different types for UI variety.
            alternates: list[dict[str, str]] = []
            seen_types: set[str] = {kind}
            for group_name in ("partial_match", "branded", "generic", "naked_url"):
                if group_name in seen_types:
                    continue
                for alt in candidates.get(group_name, []):
                    if alt and alt != primary:
                        alternates.append({"anchor": alt, "type": group_name})
                        seen_types.add(group_name)
                        break
                if len(alternates) >= 2:
                    break
            suggestion["anchor_alternates"] = alternates
