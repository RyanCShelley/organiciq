from __future__ import annotations

from typing import Any

FEATURE_LABELS: dict[str, str] = {
    "sge": "AI Overview",
    "reviews": "Reviews",
    "gmb": "Business Profile",
    "sitelinks": "Sitelinks",
    "local_pack": "Local Pack",
    "maps": "Maps",
    "people_also_ask": "People Also Ask",
    "featured_snippets": "Featured Snippet",
    "video": "Video",
    "top_stories": "Top Stories",
    "images": "Images",
    "faq": "FAQ",
    "knowledge_graph": "Knowledge Graph",
    "shopping_results": "Shopping",
}


def earned_codes_from_features(features: dict[str, Any] | None) -> list[str]:
    if not isinstance(features, dict):
        return []
    return [code for code, held in features.items() if held is True]


def earned_codes_from_position(position: dict[str, Any] | None) -> list[str]:
    if not isinstance(position, dict):
        return []
    codes: list[str] = []
    if position.get("is_map") in {1, True}:
        codes.append("local_pack")
    map_position = position.get("map_position")
    if isinstance(map_position, (int, float)) and map_position > 0:
        if "local_pack" not in codes:
            codes.append("local_pack")
    return codes


def merge_earned_serp_features(*sources: list[str] | dict[str, Any] | None) -> list[str] | None:
    merged: list[str] = []
    for source in sources:
        if isinstance(source, list):
            merged.extend(source)
        elif isinstance(source, dict):
            if "earned_serp_features" in source and isinstance(source["earned_serp_features"], list):
                merged.extend(source["earned_serp_features"])
            merged.extend(earned_codes_from_features(source.get("features")))
            merged.extend(earned_codes_from_position(source))
    deduped = list(dict.fromkeys(merged))
    return deduped or None


def label_earned_serp_features(codes: list[str] | None) -> list[str]:
    if not codes:
        return []
    return [FEATURE_LABELS.get(code, code.replace("_", " ").title()) for code in codes]


def extract_features_by_keyword(payload: Any) -> dict[tuple[str, str], list[str]]:
    """Map (site_engine_id, keyword_id) -> earned SERP feature codes from positions payloads."""
    result: dict[tuple[str, str], list[str]] = {}

    def ingest_keyword(keyword: dict[str, Any], engine_id: str | None) -> None:
        keyword_id = str(keyword.get("id") or keyword.get("keyword_id") or "").strip()
        if not keyword_id:
            return
        engine = str(keyword.get("site_engine_id") or engine_id or "").strip()
        codes = earned_codes_from_features(keyword.get("features"))
        positions = keyword.get("positions")
        if isinstance(positions, list) and positions:
            latest = positions[-1]
            if isinstance(latest, dict):
                codes = list(dict.fromkeys(codes + earned_codes_from_position(latest)))
        if codes:
            result[(engine, keyword_id)] = codes

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            engine_id = str(item.get("site_engine_id") or "").strip() or None
            nested_keywords = item.get("keywords")
            if isinstance(nested_keywords, list):
                for keyword in nested_keywords:
                    if isinstance(keyword, dict):
                        ingest_keyword(keyword, engine_id)
                continue
            ingest_keyword(item, engine_id)
    elif isinstance(payload, dict):
        if isinstance(payload.get("keywords"), list):
            engine_id = str(payload.get("site_engine_id") or "").strip() or None
            for keyword in payload["keywords"]:
                if isinstance(keyword, dict):
                    ingest_keyword(keyword, engine_id)

    return result
