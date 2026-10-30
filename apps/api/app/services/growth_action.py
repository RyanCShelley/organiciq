"""A growth action: one page, worked for one topic, as a single piece of work.

The plan sells growth actions by the page: one, three or five pages a month. So a growth action is
not a single rule's advice but everything worth doing to one page for one topic, bundled:

- the core three: answer the question at the top (A-1), say it in the words people search (S-1),
  and add a short FAQ (S-2, or the page's FAQ markup, V-7);
- what else the page read says applies: the snippet (S-5), the opening (P-1), links from related
  pages (S-4), or a rule's own prescription.

A part is included only when the page and its data give it something to do. A core part that has
nothing to do is named as such, with the reason, and is not padded in.

The topic is a watchlist keyword. The page is chosen by the tool, with the reasons shown, and a
person can choose another.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.decisions import visibility_candidates as vc
from app.decisions.provisional import _opening, _tokens
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.services import llm_evidence

#: A page whose title already says the topic counts for this much more than its impressions alone.
FIT_WEIGHT = 1.5
#: Parts that join the bundle when the page read produces them, in the order they are listed.
CORE = ("A-1", "S-1", "S-2", "V-7")
EXTRAS = ("S-5", "P-1", "S-4")
PART_ORDER = ("A-1", "S-1", "S-2", "V-7", "P-1", "S-5", "S-4")

PART_NAMES = {
    "A-1": "Answer the question at the top",
    "S-1": "Use the phrasing people search",
    "S-2": "Add a short FAQ",
    "V-7": "Mark up the FAQ",
    "P-1": "Rewrite the opening",
    "S-5": "Reread the title and description",
    "S-4": "Link here from related pages",
}


def _key(keyword: str) -> str:
    return " ".join(keyword.lower().split())


def topic_pages(db: Session, client: Client, month: str, keyword: str) -> dict[str, Any]:
    """The pages that show for searches containing `keyword`, with the one the tool would work on first.

    Brand searches are left out: no page work moves them. A page scores its impressions, times 1.5
    when its title already says the topic. The reasons are returned so a person can overrule it.
    """
    kw = _key(keyword)
    year, mon = int(month[:4]), int(month[5:7])
    start, end = vc.windows(date(year, mon, 1))["current"]
    rows = vc._aggregate(db, client.id, start, end, [kw])
    brand = vc.brand_keys(client)

    pages: dict[str, dict[str, Any]] = defaultdict(lambda: {"impressions": 0.0, "clicks": 0.0, "weighted": 0.0, "searches": 0, "top": ("", 0.0)})
    for (text, url), n in rows.items():
        if vc.is_brand(text, brand):
            continue
        p = pages[url]
        p["impressions"] += n["impressions"]
        p["clicks"] += n["clicks"]
        p["weighted"] += n["position"] * n["impressions"]
        p["searches"] += 1
        if n["impressions"] > p["top"][1]:
            p["top"] = (text, n["impressions"])

    titles = {
        url: title
        for url, title in db.query(FactCrawlPageSnapshot.normalized_url, FactCrawlPageSnapshot.title).filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageSnapshot.normalized_url.in_(list(pages)),
        )
    }
    wanted = _tokens(kw)
    out = []
    for url, p in pages.items():
        title = titles.get(url) or ""
        fit = bool(wanted) and wanted <= _tokens(title)
        impressions = p["impressions"]
        out.append(
            {
                "url": url,
                "impressions": round(impressions),
                "clicks": round(p["clicks"]),
                "position": round(p["weighted"] / impressions, 1) if impressions else None,
                "searches": p["searches"],
                "top_search": p["top"][0],
                "title": title,
                "title_says_topic": fit,
                "score": round(impressions * (FIT_WEIGHT if fit else 1.0), 1),
            }
        )
    out.sort(key=lambda r: -r["score"])
    return {
        "keyword": kw,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "recommended": out[0]["url"] if out else None,
        "pages": out[:8],
        "total_pages": len(out),
        "rule": f"Impressions for searches containing “{kw}” over three months, counted {FIT_WEIGHT:g}× when the page's title already says the topic. Brand searches are left out.",
    }


def _part(id_: str, source: dict[str, Any], *, core: bool) -> dict[str, Any]:
    return {
        "id": id_,
        "name": PART_NAMES[id_],
        "title": source.get("title") or PART_NAMES[id_],
        "why": source.get("why") or "",
        "steps": list(source.get("steps") or []),
        "evidence": list(source.get("evidence") or []),
        "core": core,
        "confirmed_by_rule": source.get("action_id") is not None,
    }


def build(
    db: Session,
    client: Client,
    month: str,
    keyword: str,
    *,
    page: str | None,
    diagnose,
    evidence_for,
) -> dict[str, Any]:
    """Diagnose the chosen page for the topic and bundle what applies into one growth action.

    `diagnose(search, url, row, evidence)` and `evidence_for(search, url)` are the page reader and the
    evidence builder, passed in so this module stays free of HTTP and of the router.
    """
    topic = topic_pages(db, client, month, keyword)
    if not topic["pages"]:
        return {"ok": False, "error": f"No page shows for a search containing “{topic['keyword']}” in Search Console over the last three months."}
    chosen = next((p for p in topic["pages"] if p["url"] == page), None) if page else topic["pages"][0]
    if chosen is None:
        return {"ok": False, "error": "That page does not show for this topic."}
    search = chosen["top_search"]
    row = vc.lookup_pair(db, client, month, search, chosen["url"])
    if row is None:
        return {"ok": False, "error": "The page's numbers for this topic could not be worked out."}

    result = diagnose(search, chosen["url"], row, evidence_for(search, chosen["url"]))
    if not result["read"]["ok"]:
        return {"ok": False, "error": f"The page could not be read: {result['read'].get('error') or 'it did not load'}.", "topic": topic}

    found: dict[str, dict[str, Any]] = {}
    for s in result["suggestions"]:
        found[s["id"]] = s
    for p in result["prescriptions"]:
        found[p["action_id"]] = {**p, "steps": p.get("steps") or []}

    parts: list[dict[str, Any]] = []
    left_out: list[dict[str, str]] = []
    skipped = {s["id"]: s["reason"] for s in result["skipped_suggestions"]}
    paired = llm_evidence.paired_keyword(db, client, search)

    for id_ in PART_ORDER:
        if id_ in found:
            parts.append(_part(id_, found[id_], core=id_ in CORE))

    # A core part with nothing from the page read can still be built from the topic's paired question.
    have = {p["id"] for p in parts}
    if "A-1" not in have and paired is not None:
        prompt = " ".join(paired.paired_ai_prompt.split())
        parts.insert(
            0,
            {
                "id": "A-1", "name": PART_NAMES["A-1"], "core": True, "confirmed_by_rule": False,
                "title": f"Answer “{prompt}” at the top of the page",
                "why": "This is the question the topic's paired prompt asks the AI platforms. " + skipped.get("A-1", ""),
                "steps": [
                    f"The question: “{prompt}”.",
                    "Write a two to three sentence answer, in plain words a customer would use, directly under the main heading.",
                    "Use only facts already true of this page and product.",
                ],
                "evidence": [],
            },
        )
    elif "A-1" not in have:
        left_out.append({"id": "A-1", "reason": skipped.get("A-1", "No paired question for this topic.")})
    if "S-1" not in have:
        left_out.append({"id": "S-1", "reason": "The page's title and main heading already say the phrasing people search, or no longer phrasing shows for it."})
    if "S-2" not in have and "V-7" not in have:
        if paired is not None:
            prompt = " ".join(paired.paired_ai_prompt.split())
            parts.append(
                {
                    "id": "S-2", "name": PART_NAMES["S-2"], "core": True, "confirmed_by_rule": False,
                    "title": "Add a short FAQ",
                    "why": "No question-shaped search shows for the page, so the topic's paired question is the starting point. " + skipped.get("S-2", ""),
                    "steps": [
                        f"Start with the question customers ask AI platforms: “{prompt}”.",
                        "Add three to five questions a customer would ask before buying, each answered in one to three sentences.",
                        "Then mark the FAQ up as FAQPage.",
                    ],
                    "evidence": [],
                }
            )
        else:
            left_out.append({"id": "S-2", "reason": skipped.get("S-2", "No question to base an FAQ on.")})

    parts.sort(key=lambda p: PART_ORDER.index(p["id"]))
    seen = {p["id"] for p in parts}
    also = [{"id": s["id"], "title": s["title"]} for s in result["suggestions"] if s["id"] not in seen and s["id"] not in EXTRAS + CORE]
    return {
        "ok": True,
        "topic": topic,
        "keyword": topic["keyword"],
        "page": chosen["url"],
        "chosen": chosen,
        "search": search,
        "row": row,
        "parts": parts,
        "left_out": left_out,
        "also_seen": also,
        "observations": result["observations"],
        "opening": _opening_text(result),
    }


def _opening_text(result: dict[str, Any]) -> str | None:
    facts = result.get("page_facts") or {}
    return facts.get("h1")


def draft(bundle: dict[str, Any], month: str) -> dict[str, Any]:
    """The bundle as the task body: one title, the reasons, and every part's steps as a checklist."""
    parts = bundle["parts"]
    chosen = bundle["chosen"]
    path = bundle["page"].split("//", 1)[-1].split("/", 1)[-1]
    steps: list[str] = []
    for i, p in enumerate(parts, start=1):
        steps.append(f"# {i}. {p['name']}")
        steps.extend(p["steps"])
    evidence = [f"{chosen['impressions']:,} impressions for searches containing “{bundle['keyword']}”, best position {chosen['position']}"]
    for p in parts:
        evidence.extend(f"{p['id']}: {line}" for line in p["evidence"])
    return {
        "month": month,
        "kind": "growth_action",
        "rule_id": "GA",
        "search": bundle["keyword"],
        "page": bundle["page"],
        "title": f"Growth action: /{path} for “{bundle['keyword']}”",
        "why": (
            f"This page gets the most impressions for “{bundle['keyword']}” ({chosen['impressions']:,} over three months). "
            f"The work is {len(parts)} part{'s' if len(parts) != 1 else ''}, done together on this one page: "
            + ", ".join(p["name"].lower() for p in parts)
            + "."
        ),
        "steps": steps,
        "done_when": "Every part above is live on the page.",
        "metric": f"Clicks and impressions for searches containing “{bundle['keyword']}” in Search Console, and whether the AI platforms cite the page in next month's LLM visibility run",
        "evidence": evidence,
    }
