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

import re
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.decisions import action_context as ac
from app.decisions import serp_intent
from app.decisions import visibility_candidates as vc
from app.decisions.provisional import _opening, _tokens
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageSnapshot
from app.services import llm_evidence

#: A page whose title already says the topic counts for this much more than its impressions alone.
FIT_WEIGHT = 1.5
#: How many pages of a topic are listed (the highest scoring), plus the page the person came from.
PAGES_SHOWN = 50
#: Statuses that say the host would not serve our crawler, not that the page is missing or broken.
_TURNED_AWAY = frozenset({401, 403, 429, 503})
#: Parts that join the bundle when the page read produces them, in the order they are listed.
CORE = ("A-1", "S-1", "S-2", "V-7")
EXTRAS = ("P-1", "S-5", "S-4")
#: Parts that are never selected for the person: offered, and theirs to add. FAQ markup is not a growth lever by default.
NOT_DEFAULT = ("V-7",)
#: Parts that a link count alone used to produce. Links are suggested by the internal link tool, on relatedness.
NOT_BY_COUNT = ("V-4", "S-4")
#: Suggestions that are not offered at all here: S-6 asks which page should own the topic, and choosing the
#: page is what this screen does.
NOT_OFFERED = ("S-6",)

PART_NAMES = {
    "A-1": "Answer the question at the top",
    "S-1": "Use the phrasing people search",
    "S-2": "Add a short FAQ",
    "V-7": "Mark up the FAQ",
    "P-1": "Rewrite the opening",
    "S-5": "Reread the title and description",
    "S-4": "Link here from related pages",
    "V-4": "Add internal links",
    "IM-1": "Match the page to what the searcher wants",
    "TI-1": "Investigate crawler access",
}
#: What kind of work each part is, and what it is for. No figure is forecast for any of them.
ACTION_TYPES = {
    "A-1": "Optimize existing page", "S-1": "Optimize existing page", "S-2": "Optimize existing page", "P-1": "Optimize existing page", "S-5": "Optimize existing page",
    "V-7": "Update structured data", "S-4": "Improve internal linking", "V-4": "Improve internal linking",
    "TI-1": "Investigate technical issue", "IM-1": "Optimize existing page",
}
BENEFITS = {
    "A-1": ("AI visibility", "An answer an AI platform can lift gives it something of this site to cite."),
    "S-1": ("SEO", "A title and heading in the searched words tell the search engine and the searcher the page is about this."),
    "S-2": ("SEO and AI visibility", "Questions answered on the page can be shown and cited as answers."),
    "V-7": ("SEO and AI visibility", "Markup lets a search engine read the questions and answers as such."),
    "P-1": ("SEO", "An opening that says what the page is about holds the searcher who clicked."),
    "S-5": ("SEO", "A clearer title and description can earn more of the clicks the page is already shown for."),
    "S-4": ("SEO", "Links from related pages tell the search engine this page matters for the topic."),
    "V-4": ("SEO", "Links from related pages tell the search engine this page matters for the topic."),
    "TI-1": ("Technical reliability", "Until our reader can fetch the page, nothing about it can be checked or measured."),
    "IM-1": ("SEO and conversion", "A page that does what the searcher came to do is the page a search engine wants to show for it."),
}
#: Parts that put an explanation into the page. They are the ones a commercial page should not take for an informational search.
#: The parts that lead an action when present: what the searcher wants, or where the work was routed.
_LEADS = ("IM-1",)
#: Parts whose worth depends on what the searcher wants. With no results page read they are held back, not guessed at.
INTENT_DEPENDENT = ("A-1", "S-1", "P-1", "S-2", "PC-1", "IM-1")
#: What the page must do for each intent on each kind of page: `(what the searcher needs from it, the changes that serve that)`.
_MATCH: dict[str, dict[str, tuple[str, list[str]]]] = {
    serp_intent.TRANSACTIONAL: {
        ac.CATEGORY: ("find, compare and buy from the range", [
            "Open with one or two sentences that say what the range is and who it is for, above the products, without pushing them down.",
            "Make the attributes buyers choose by visible on each product in the list: name, the deciding specification, size, price and availability.",
            "Add or check filters and sorting for those attributes, so a shopper can narrow the range.",
            "Link each product by its name, and link out to the closest related collections.",
        ]),
        ac.PRODUCT: ("decide on and buy this product", [
            "Say in the first lines what the product is, who it is for and what sets it apart from the others in the range.",
            "State the attributes a buyer checks before buying: specifications, size, price, availability, delivery and returns.",
            "Keep the price, options and the buy button above everything that explains.",
        ]),
        ac.SERVICE: ("book or enquire about the service", [
            "Say what the service is, who it is for, where it is offered and what happens after an enquiry.",
            "Put the way to book or enquire, and the price or how pricing works, where it can be seen without scrolling far.",
            "Show proof next to it: results, reviews, accreditations.",
        ]),
    },
    serp_intent.COMMERCIAL: {
        ac.CATEGORY: ("compare the options before choosing", [
            "Add a short comparison of the products in the range by the attributes buyers weigh, as a table or a 'best for' line on each.",
            "Show reviews or ratings on the products in the list.",
            "Link to any buying guide the site has, and from it back to this range.",
        ]),
        ac.PRODUCT: ("judge this product against the alternatives", [
            "Say what this product is best for and how it differs from the nearest alternatives in the range.",
            "Show reviews, ratings and any independent proof on the page.",
        ]),
        ac.SERVICE: ("judge this provider against the alternatives", [
            "Say what makes this service different, with proof: results, case studies, reviews.",
            "Answer the comparison questions a buyer has: scope, price range, timescale.",
        ]),
        ac.ARTICLE: ("compare the options before choosing", [
            "Structure the article as the comparison it is being read for: the options, the criteria, a verdict for each kind of buyer.",
            "Link each option to its product or service page.",
        ]),
    },
    serp_intent.INFORMATIONAL: {
        ac.ARTICLE: ("understand the topic", [
            "Answer the question in the first two or three sentences, then cover what a reader asks next.",
            "Use headings that say what each section answers, so a section can be read on its own.",
        ]),
        ac.RESOURCE: ("understand the topic", [
            "Answer the question in the first two or three sentences, then cover what a reader asks next.",
            "Use headings that say what each section answers, so a section can be read on its own.",
        ]),
    },
    serp_intent.LOCAL: {
        ac.LOCATION: ("find and contact this business nearby", [
            "State the area served, the address, opening hours and phone number in text on the page.",
            "Say which services are offered at this location, with a way to book or call.",
        ]),
        ac.SERVICE: ("find this service nearby", [
            "Name the places the service is offered in the page's own text, and link to the location pages.",
            "Put the phone number and the way to book where they can be seen at once.",
        ]),
        ac.HOMEPAGE: ("find and contact this business nearby", [
            "State what the business does and the area it serves in the first lines, with the address, hours and phone number in text.",
        ]),
    },
}
#: What each consumer need asks of the page's message and proof.
_NEED_LINE = {
    "help": "lead with how it solves the practical problem, in plain steps",
    "reassure": "lead with what makes it safe, simple and trustworthy, and show the proof beside the claim",
    "educate": "explain the differences that matter so the reader can decide for themselves",
    "surprise": "show what is new or unexpected about it",
    "impress": "show quality, recognition and who else chooses it",
    "thrill": "show the experience and energy of it",
}


def _key(keyword: str) -> str:
    return " ".join(keyword.lower().split())


def resolve_topic(db: Session, client: Client, month: str, search: str, page: str) -> dict[str, Any]:
    """The topic a candidate belongs to.

    A search takes the watchlist keyword it contains (the longest), else it is its own topic. A page picked
    from the Traffic or Leads list has no search, so its topic is the search that brings it the most
    impressions (brand searches excluded), narrowed to a watchlist keyword the same way.
    """
    from sqlalchemy import func

    from app.models.gsc import FactGscQueryPage
    from app.models.watchlist import WatchlistKeyword

    keywords = sorted({_key(k.keyword) for k in db.query(WatchlistKeyword).filter(WatchlistKeyword.client_id == client.id)}, key=len, reverse=True)

    def narrow(text: str) -> tuple[str, str]:
        for kw in keywords:
            if f" {kw} " in f" {text} ":
                return kw, "the watchlist keyword it contains"
        return text, "the search itself"

    text = _key(search)
    if text and not text.startswith("("):
        keyword, source = narrow(text)
        return {"keyword": keyword, "source": source}

    year, mon = int(month[:4]), int(month[5:7])
    start, end = vc.windows(date(year, mon, 1))["current"]
    q = func.lower(func.trim(FactGscQueryPage.query))
    rows = (
        db.query(q, func.sum(FactGscQueryPage.impressions))
        .filter(FactGscQueryPage.client_id == client.id, FactGscQueryPage.normalized_url == page, FactGscQueryPage.date >= start, FactGscQueryPage.date <= end)
        .group_by(q)
        .order_by(func.sum(FactGscQueryPage.impressions).desc())
        .all()
    )
    brand = vc.brand_keys(client)
    for query_text, _ in rows:
        if not vc.is_brand(query_text, brand):
            keyword, source = narrow(query_text)
            return {"keyword": keyword, "source": f"the page's top search" + (f", narrowed to {source}" if source != "the search itself" else "")}
    return {"keyword": None, "source": "no search in Search Console brings this page impressions"}


def _window(month: str) -> tuple[date, date]:
    return vc.windows(date(int(month[:4]), int(month[5:7]), 1))["current"]


def site_pages(db: Session, client: Client) -> dict[str, str] | None:
    """Address and title of every page in the newest site crawl, or None when the site has not been crawled."""
    from sqlalchemy import func

    newest = db.query(func.max(FactCrawlPageSnapshot.snapshot_date)).filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY).scalar()
    if newest is None:
        return None
    rows = db.query(FactCrawlPageSnapshot.normalized_url, FactCrawlPageSnapshot.title).filter(
        FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot.snapshot_date == newest)
    return {url: title or "" for url, title in rows}


def _reading(signals: dict[str, Any] | None) -> dict[str, Any]:
    """The search's intent as read from its results page, or "not read" when none was passed in."""
    return (signals or {}).get("reading") or serp_intent.not_read()


def topic_pages(db: Session, client: Client, month: str, keyword: str, include: str | None = None, signals: dict[str, Any] | None = None, exact: bool = False) -> dict[str, Any]:
    """The pages that show for searches containing `keyword`, with the one the tool would work on first.

    With `exact`, only the pages that show for that one search, word for word. A growth action is about one term
    on one page; the wider list (every search containing a watchlist keyword) is for browsing a topic and must not
    stand in for the term.

    Brand searches are left out: no page work moves them. A page scores its impressions, times 1.5
    when its title already says the topic. The reasons are returned so a person can overrule it.

    A page the crawl was turned away from (no status, or a 401, 403, 429 or 503, and no title kept)
    has no title to judge. It is counted as if its title fits and marked `title_read: False`: a
    page the host would not show us must not lose the choice for a title nobody saw.
    """
    kw = _key(keyword)
    year, mon = int(month[:4]), int(month[5:7])
    start, end = vc.windows(date(year, mon, 1))["current"]
    rows = vc._aggregate(db, client.id, start, end, [kw])
    if exact:
        rows = {key: n for key, n in rows.items() if key[0] == kw}
    brand = () if exact else vc.brand_keys(client)

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

    titles: dict[str, str] = {}
    turned_away: set[str] = set()
    for url, title, status in (
        db.query(FactCrawlPageSnapshot.normalized_url, FactCrawlPageSnapshot.title, FactCrawlPageSnapshot.status_code).filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageSnapshot.normalized_url.in_(list(pages)),
        )
        .order_by(FactCrawlPageSnapshot.snapshot_date)
    ):
        titles[url] = title
        turned_away.discard(url)
        if not title and (status is None or status in _TURNED_AWAY):
            turned_away.add(url)
    wanted = _tokens(kw)
    kinds = {url: ac.classify_page(url, title=titles.get(url) or "") for url in pages}
    intent = _reading(signals)
    out = []
    for url, p in pages.items():
        title = titles.get(url) or ""
        kind = kinds[url]
        fit = ac.compatibility(intent, kind)
        title_read = url not in turned_away
        fits_title = bool(wanted) and wanted <= _tokens(title)
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
                "title_says_topic": fits_title,
                "title_read": title_read,
                "score": round(impressions * (FIT_WEIGHT if fits_title or not title_read else 1.0), 1),
                "page_type": kind["type"], "page_type_name": kind["name"], "fit": fit["level"], "fit_why": fit["why"],
            }
        )
    # Suitability first, then the score: a page that does not suit the search does not win on impressions.
    out.sort(key=lambda r: (r["fit"] == ac.LOW, -r["score"]))
    shown = out[:PAGES_SHOWN]
    # The page being planned from is always on the list, however few impressions it has: it is the one a person came to choose.
    if include and all(r["url"] != include for r in shown):
        shown += [r for r in out if r["url"] == include]
    return {
        "keyword": kw,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "recommended": out[0]["url"] if out else None,
        "pages": shown,
        "total_pages": len(out),
        "intent": intent,
        "unsuitable": sum(1 for r in out if r["fit"] == ac.LOW),
        "rule": f"Impressions for searches containing “{kw}” over three months, counted {FIT_WEIGHT:g}× when the page's title already says the topic, or when the site turned our crawler away from the page so its title is not known. Brand searches are left out. A page whose type does not suit the search's intent is listed after the ones that do, whatever its impressions.",
    }


def _plain(line: str) -> str:
    """Evidence lines come from the shared rules and can name a table; a person reading the task should not meet that."""
    return line.replace("facts_crawl_internal_links:", "From the site crawl:")


def _part(id_: str, source: dict[str, Any], *, core: bool) -> dict[str, Any]:
    return {
        "id": id_,
        "name": PART_NAMES.get(id_) or (source.get("title") or id_),
        "title": source.get("title") or PART_NAMES.get(id_) or id_,
        "why": source.get("why") or "",
        "steps": list(source.get("steps") or []),
        "evidence": [_plain(e) for e in source.get("evidence") or []],
        "core": core,
        "confirmed_by_rule": source.get("action_id") is not None,
        "action_type": source.get("action_type") or ACTION_TYPES.get(id_) or ("Improve conversion path" if id_.startswith("F-") else "Optimize existing page"),
        "benefit": source.get("benefit") or BENEFITS.get(id_, ("SEO", ""))[0],
        "benefit_why": source.get("benefit_why") or BENEFITS.get(id_, ("", ""))[1],
    }


def _evidence(read: dict[str, Any], intent: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    """Where the page's facts came from, how far they can be trusted, and what is assumed and not checked."""
    outcome = read.get("outcome") or "read"
    source = read.get("evidence_source") or "live"
    unverified: list[str] = []
    if source == "crawl":
        day = read.get("crawl_date") or "an earlier date"
        unverified.append(f"The page was not read live ({ac.OUTCOME_NAMES[outcome].lower()}). Its facts are from the site crawl of {day}, which holds the title, description, headings, the first paragraph under each heading and markup. What is live now may differ.")
    if not ac.is_read(intent):
        unverified.append(f"{intent['name']}. {intent.get('uncertainty') or ''} Recommendations that depend on intent are held back.".replace("  ", " "))
    elif intent.get("uncertainty"):
        unverified.append(f"About the results page: {intent['uncertainty']}")
    if template["shared"] is None:
        unverified.append(template["note"])
    confidence = "low" if source == "none" else "medium" if source == "crawl" or intent["confidence"] in ("low", "none") else "high"
    if source != "none" and not ac.is_read(intent):
        confidence = "medium"
    return {
        "crawl_status": outcome, "crawl_status_name": ac.OUTCOME_NAMES[outcome], "source": source, "crawl_date": read.get("crawl_date"),
        "confidence": confidence, "sufficient": source in ("live", "crawl"), "unverified": unverified,
        "summary": {"live": "The page was read live.", "crawl": f"The page was not read live; the site crawl of {read.get('crawl_date')} is used.", "none": "The page could not be read and no earlier copy is held."}[source],
    }


def _investigation(chosen: dict[str, Any], topic: dict[str, Any], read: dict[str, Any], received: str | None) -> dict[str, Any]:
    """The part offered when our reader was stopped and nothing is held to judge the page by.

    Nothing about the page's content is stated: it was not seen. The refusal is the finding, and what it
    means for search engines is said only as far as the evidence goes.
    """
    outcome = read.get("outcome") or "other"
    finding = ac.technical_finding(outcome, impressions=int(chosen["impressions"]), window_to=topic["window"]["to"])
    seen = read.get("blocked") or read.get("error") or "the page did not load"
    return {
        "id": "TI-1", "name": PART_NAMES["TI-1"], "core": True, "confirmed_by_rule": False,
        "title": f"Investigate why our reader cannot fetch this page ({ac.OUTCOME_NAMES[outcome].lower()})",
        "why": f"{finding['classification']}. {finding['impact']}",
        "steps": [
            "Open the page in a browser, signed out, and confirm it loads for a visitor.",
            "In Search Console, run URL Inspection on the page and record whether Google can fetch and index it.",
            "Read robots.txt for rules that name crawlers, and the host's firewall, CDN or bot-protection settings for rules that block unknown crawlers.",
            "If the block is a bot rule, ask the host to allow OrganicIQBot, then read the page again here.",
            "Do not change the page's content on the strength of this action: it has not been read.",
        ],
        "evidence": [f"What our reader got: {seen}", *([received] if received else []), finding["google"]],
        "action_type": ACTION_TYPES["TI-1"], "benefit": BENEFITS["TI-1"][0], "benefit_why": BENEFITS["TI-1"][1],
        "classification": finding["classification"],
    }


def _existing_page(topic: dict[str, Any], site: dict[str, str] | None, keyword: str, chosen_url: str, kinds: frozenset[str]) -> dict[str, Any] | None:
    """A page of this site, of one of `kinds`, that already covers the topic: one that shows for it, or one whose title says it."""
    showing = [p for p in topic["pages"] if p["url"] != chosen_url and p["page_type"] in kinds]
    if showing:
        best = max(showing, key=lambda p: p["impressions"])
        return {"url": best["url"], "title": best["title"], "how": f"it already shows for this topic ({best['impressions']:,} impressions)"}
    wanted = _tokens(keyword)
    for url, title in (site or {}).items():
        if url != chosen_url and wanted and wanted <= _tokens(title) and ac.classify_page(url, title=title)["type"] in kinds:
            return {"url": url, "title": title, "how": "its title says the topic"}
    return None


def _suggested_page(topic: dict[str, Any], site: dict[str, str] | None, chosen: dict[str, Any], kind: dict[str, Any], fit: dict[str, Any], wants: str | None) -> dict[str, Any]:
    """The page of the right kind for a search this page does not suit. Named for the person to review on its own.

    Never switched to and never worked on inside this action. Where the site has no such page, that is said, and
    whether to make one is left as a separate decision: the format that ranks informs it and does not dictate it.
    """
    kinds = ac.INFORMATIONAL_PAGES if wants == "article" else ac.COMMERCIAL_PAGES if wants == "selling page" else None
    found = _existing_page(topic, site, topic["keyword"], chosen["url"], kinds) if kinds else None
    if found is None:
        better = _better_page(topic, chosen, fit)
        found = {"url": better["url"], "title": next((p["title"] for p in topic["pages"] if p["url"] == better["url"]), ""), "how": f"it shows for this search and suits it better ({better['impressions']:,} impressions)"} if better else None
    what = {"article": "an article or guide", "selling page": "a product, collection or service page"}.get(wants or "", "a different kind of page")
    if found:
        return {
            "kind": wants, "exists": True, "url": found["url"], "title": found["title"],
            "why": f"This search is better served by {what}, and one already exists: {found['how']}.",
            "next": "Review that page on its own. This action is not moved to it.",
        }
    checked = "none shows for it in Search Console and none in the site crawl says the topic in its title" if site is not None else "none shows for it in Search Console, and the site has not been crawled, so check before deciding"
    return {
        "kind": wants, "exists": False, "url": None, "title": None,
        "why": f"This search is better served by {what}. This site has none for it: {checked}.",
        "next": "Whether to create one is a separate decision. Nothing is planned for it here.",
    }


def _intent_match(search: str, intent: dict[str, Any], kind: dict[str, Any]) -> dict[str, Any] | None:
    """The part that says what the searcher wants and what this kind of page must do about it.

    Built only from a results page that was read. Its evidence is what was seen on that page; the consumer need, when
    one was found, shapes the message and is marked as observed or inferred.
    """
    if not ac.is_read(intent):
        return None
    # The primary intent only. Borrowing the secondary one's advice told a blog post to "help them understand the topic"
    # for a search read as transactional. A mixed search has two leading intents, so either may be matched.
    found = None
    for i in ((intent["primary"], intent.get("secondary")) if intent["intent"] == serp_intent.MIXED else (intent["primary"],)):
        found = _MATCH.get(i or "", {}).get(kind["type"])
        if found:
            break
    if not found:
        return None
    wants, steps = found
    steps = list(steps)
    styles = intent.get("content_styles") or {}
    types = intent.get("content_types") or {}
    if intent.get("content_to_match"):
        steps.append(f"What ranks for this search: {intent['content_to_match']}")
    need = intent.get("consumer_need")
    if need:
        steps.append(f"Message ({need['name']}, {need['basis']}): {_NEED_LINE[need['need']]}.")
    evidence = list(intent["evidence"])
    if types:
        evidence.append("Ranking content types: " + ", ".join(f"{n} {t}" for t, n in types.items()) + ".")
    if styles:
        evidence.append("Ranking content styles: " + ", ".join(f"{n} {t}" for t, n in styles.items()) + ".")
    if need:
        evidence.append(f"Consumer need ({need['basis']}): {need['evidence']}")
    return {
        "id": "IM-1", "name": PART_NAMES["IM-1"], "core": True, "confirmed_by_rule": False,
        "title": f"Help the searcher {wants}",
        "why": f"{intent.get('searcher_goal') or ''} The results page for “{search}” was read as {intent['name'].lower()}, and a {kind['name'].lower()} serves that by helping them {wants}.".strip(),
        "steps": steps, "evidence": evidence,
        "action_type": ACTION_TYPES["IM-1"], "benefit": BENEFITS["IM-1"][0], "benefit_why": BENEFITS["IM-1"][1],
    }


_SERVES = {"search": "SEO", "llm": "AI visibility", "both": "SEO and AI visibility"}


def _gap_part(n: int, gap: dict[str, Any], intent_read: bool) -> dict[str, Any]:
    """One thing the winners do that this page does not, as a part: the issue, the evidence, the change, what to expect and how to check."""
    name = gap["change"].split(". ")[0].rstrip(".")
    return {
        "id": f"W-{n}", "name": name if len(name) <= 90 else name[:87].rstrip() + "…", "core": True, "confirmed_by_rule": False,
        "title": gap["change"], "why": gap["issue"],
        "steps": [gap["change"], *([f"Expected: {gap['expected_outcome']}"] if gap["expected_outcome"] else []), *([f"Check afterwards: {gap['validation']}"] if gap["validation"] else [])],
        "evidence": [f"{'Observed' if gap['basis'] == 'observed' else 'Inferred'} from the winning pages: {gap['evidence']}", "Seen on: " + ", ".join(gap["seen_on"])],
        "action_type": "Optimize existing page", "benefit": _SERVES[gap["serves"]],
        "benefit_why": gap["expected_outcome"], "basis": gap["basis"], "serves": gap["serves"],
    }


_FIT_RANK = {ac.HIGH: 0, ac.MEDIUM: 1, ac.UNVERIFIED: 2, ac.LOW: 3}


def _better_page(topic: dict[str, Any], chosen: dict[str, Any], fit: dict[str, Any]) -> dict[str, Any] | None:
    """Another page of this site that shows for the same term and suits it better. Named for the person to consider; never switched to."""
    mine = _FIT_RANK[fit["level"]]
    better = [p for p in topic["pages"] if p["url"] != chosen["url"] and _FIT_RANK.get(p["fit"], 2) < mine and _FIT_RANK.get(p["fit"], 2) <= 1]
    if not better:
        return None
    best = min(better, key=lambda p: (_FIT_RANK[p["fit"]], -p["impressions"]))
    return {"url": best["url"], "fit": best["fit"], "impressions": best["impressions"], "why": best["fit_why"]}


def _duplicate(db: Session, client: Client, planned_month: str | None, keyword: str, page: str) -> str | None:
    if not planned_month:
        return None
    from app.models.engine_task import EngineTask

    row = db.query(EngineTask.title).filter(
        EngineTask.client_id == client.id, EngineTask.month == planned_month, EngineTask.kind == "growth_action",
        EngineTask.search == keyword, EngineTask.page_url == page, EngineTask.status != "dropped",
    ).first()
    return row[0] if row else None


def build(
    db: Session,
    client: Client,
    month: str,
    keyword: str,
    *,
    page: str | None,
    diagnose,
    evidence_for,
    extra_suggestions: list[dict[str, Any]] | None = None,
    signals_for=None,
    planned_month: str | None = None,
    search: str | None = None,
    winners_for=None,
) -> dict[str, Any]:
    """Diagnose one page for one term and bundle what applies into one growth action.

    `search` is the term the person selected and `page` the page they selected. Both are used exactly as given:
    the results page read is that term's, the page worked on is that page. `keyword` is the watchlist keyword the
    term is grouped under, kept as a label. The engine used to swap the term for the watchlist keyword to pick a
    "best page", then swap it again for that page's top search to read intent, so the advice was for a search
    nobody chose on a page nobody chose. If another page would serve the term better it is named in
    `better_page`; it is never switched to.

    Without `search` (a page picked from the Traffic or Leads list has none) the page's top search for the
    watchlist keyword is used, and `search_source` says so.

    `diagnose(search, url, row, evidence)` and `evidence_for(search, url)` are the page reader and the
    evidence builder, passed in so this module stays free of HTTP and of the router. `signals_for(search)`
    returns what is held about the search beyond its words: `{vendor_intents, serp_item_types, serp_date}`.

    Before anything is bundled the search's intent and the page's type are established, and the two are
    compared. A commercial page that shows for a search asking for an explanation is not rewritten to
    explain: the work is routed to a supporting article. A page our reader could not fetch, with no earlier
    copy held, gets an investigation and nothing else. The bundle then has to pass `action_context.validate`.
    """
    term = _key(search) if search and not _key(search).startswith("(") else None
    if term:
        signals = signals_for(term) if signals_for else None
        topic = topic_pages(db, client, month, term, include=page, signals=signals, exact=True)
        if not topic["pages"]:
            return {"ok": False, "error": f"No page shows for “{term}” in Search Console over the last three months."}
        chosen = next((p for p in topic["pages"] if p["url"] == page), None) if page else topic["pages"][0]
        if chosen is None:
            return {"ok": False, "error": f"That page does not show for “{term}” in Search Console over the last three months."}
        search, search_source = term, "the search you selected"
    else:
        topic = topic_pages(db, client, month, keyword, include=page, signals=None)
        if not topic["pages"]:
            return {"ok": False, "error": f"No page shows for a search containing “{topic['keyword']}” in Search Console over the last three months."}
        chosen = next((p for p in topic["pages"] if p["url"] == page), None) if page else topic["pages"][0]
        if chosen is None:
            return {"ok": False, "error": "That page does not show for this topic."}
        search, search_source = chosen["top_search"], "this page's top search for the watchlist keyword (no search was selected)"
        signals = signals_for(search) if signals_for else None
    topic["label"] = _key(keyword)
    row = vc.lookup_pair(db, client, month, search, chosen["url"])
    if row is None:
        return {"ok": False, "error": "The page's numbers for this search could not be worked out."}

    site = site_pages(db, client)
    intent = _reading(signals)
    # The reading must be of the term on the screen. One that is not is worth nothing here, and is not used.
    if intent.get("search") and _key(intent["search"]) != _key(search):
        intent = serp_intent.not_read(f"The results page returned was for “{intent['search']}”, not “{search}”, so it was not used.")
    page_evidence = evidence_for(search, chosen["url"])
    result = diagnose(search, chosen["url"], row, page_evidence)
    read = result["read"]
    facts = result.get("page_facts") or {}
    stopped = not read.get("ok") or bool(read.get("blocked"))
    if stopped:
        read = {**read, "evidence_source": "none", "outcome": read.get("outcome") or "other"}
    kind = ac.classify_page(chosen["url"], schema_types=facts.get("schema_types"), title=facts.get("title") or chosen["title"], h1=facts.get("h1"))
    fit = ac.compatibility(intent, kind)
    template = ac.template_of(chosen["url"], kind["type"], list(site) if site is not None else None)
    evidence = _evidence(read, intent, template)
    duplicate = _duplicate(db, client, planned_month, topic["keyword"], chosen["url"])

    def finish(parts: list[dict[str, Any]], left_out: list[dict[str, str]], optional: list[dict[str, Any]], *, mismatch: bool, observations: list[dict[str, Any]], suggested: dict[str, Any] | None = None, held: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        held = held or []
        for p in parts + optional + held:
            p.update(ac.scope_of(p["id"], template))
        for p in held:
            p["role"] = "held"
        # One primary action; the rest support it. What is offered but not selected stays optional.
        for n, p in enumerate(parts):
            p["role"] = "primary" if n == 0 else "supporting"
        for p in optional:
            p["role"] = "optional"
        gate = ac.validate(intent=intent, page=kind, fit=fit, evidence=evidence, template=template, parts=parts, mismatch=mismatch, duplicate_of=duplicate)
        context = {
            "intent": intent, "page_type": kind, "fit": fit, "template": template, "evidence": evidence, "validation": gate, "mismatch": mismatch,
            "action_types": list(dict.fromkeys(p["action_type"] for p in parts)),
            "benefits": list(dict.fromkeys(p["benefit"] for p in parts)),
        }
        context["winners"] = winners
        base = {
            "topic": topic, "keyword": topic["label"], "page": chosen["url"], "chosen": chosen, "search": search, "search_source": search_source,
            "row": row, "context": context, "better_page": None if mismatch else _better_page(topic, chosen, fit), "suggested_page": suggested,
        }
        done = {"left_out": left_out, "optional": optional, "observations": observations, "opening": _opening_text(result), "held": held}
        if duplicate:
            return {**base, "ok": False, "error": gate["summary"], "left_out": left_out}
        if not parts:
            # A finding does not have to produce work. Nothing recommended is an answer, with its reason, and not an error.
            reason = (
                f"{fit['why']} No change to this page is recommended for this search." if mismatch
                else "Nothing was found on this page to change for this search."
            )
            return {**base, "ok": True, "parts": [], **done, "nothing_recommended": {"reason": reason}}
        if gate["verdict"] == ac.REJECT:
            return {**base, "ok": False, "error": gate["summary"], "left_out": left_out}
        return {**base, "ok": True, "parts": parts, **done, "nothing_recommended": None}

    winners: dict[str, Any] | None = None
    if stopped:
        received = ((read.get("received") or {}).get("status"))
        return finish([_investigation(chosen, topic, read, f"HTTP {received} was returned." if received else None)], [], [], mismatch=False, observations=result.get("observations") or [])

    found: dict[str, dict[str, Any]] = {}
    for s in result["suggestions"]:
        found[s["id"]] = s
    for p in result["prescriptions"]:
        found[p["action_id"]] = {**p, "steps": p.get("steps") or []}

    parts: list[dict[str, Any]] = []
    left_out: list[dict[str, str]] = []
    skipped = {s["id"]: s["reason"] for s in result["skipped_suggestions"]}
    paired = llm_evidence.paired_keyword(db, client, search)
    prompt = " ".join(paired.paired_ai_prompt.split()) if paired is not None else ""

    read_intent = ac.is_read(intent)
    # This page is not the kind that ranks for the search. No work for the search is placed on it, and none is moved to
    # another page inside this action: the page of the right kind is named separately, for the person to review on its own.
    # What stays is only what stands on the page's own evidence, whatever the search (the conversion parts of a page
    # picked from the Traffic or Leads list).
    mismatch = read_intent and fit["level"] == ac.LOW
    if mismatch:
        explains = kind["type"] in ac.INFORMATIONAL_PAGES
        wants = "article" if not explains and (fit.get("leads") == ac.EXPLAINING or (fit.get("leads") is None and intent["primary"] == ac.INFORMATIONAL)) else \
            "selling page" if explains and (fit.get("leads") == ac.SELLING or (fit.get("leads") is None and intent["primary"] in (ac.TRANSACTIONAL, ac.LOCAL))) else None
        own = [_part(extra["id"], extra, core=False) for extra in extra_suggestions or []]
        considered = [
            {"id": id_, "name": PART_NAMES.get(id_) or found[id_].get("title") or id_, "reason": f"Not recommended here: {fit['why']} Work for this search belongs on the kind of page that ranks for it."}
            for id_ in found
        ]
        return finish(own, considered, [], mismatch=True, observations=result["observations"], suggested=_suggested_page(topic, site, chosen, kind, fit, wants))

    # A product or collection page opens with what is for sale. A question answered at its top displaces that, whatever the
    # search and whatever the question, so it is never added there automatically.
    no_top_answer = kind["type"] in (ac.PRODUCT, ac.CATEGORY)
    # Words in the search that the page never uses. On a commercial page that can be demand for something the product is not.
    missing = [t for t in facts.get("search_terms_missing") or []]
    claim_risk = bool(missing) and kind["type"] in ac.COMMERCIAL_PAGES
    barred: dict[str, str] = {}
    if not read_intent:
        # No results page, no intent, and so nothing that depends on what the searcher wants. What stands on other evidence carries on.
        for id_ in INTENT_DEPENDENT:
            barred[id_] = f"Held: {intent['name']}. This part depends on what the searcher wants, which has not been read."
    elif intent["primary"] in (serp_intent.TRANSACTIONAL, serp_intent.LOCAL, serp_intent.NAVIGATIONAL) and kind["type"] not in ac.INFORMATIONAL_PAGES:
        # Someone here to buy, book or reach a site is not helped by an answer or a rewritten opening built for a reader.
        for id_ in ("A-1", "P-1"):
            barred[id_] = f"Not added: the search is {intent['name'].lower()}, so an explanation at the top of a {kind['name'].lower()} does not serve it."
    if read_intent and no_top_answer and "A-1" not in barred:
        barred["A-1"] = f"Not added: a {kind['name'].lower()} opens with what is for sale, and a question answered at the top displaces that. A brief clarification in the page's description is offered below instead."
    if claim_risk and "S-1" not in barred:
        words = ", ".join(f"“{w}”" for w in missing[:4])
        barred["S-1"] = f"Not added: the search uses words this page never does ({words}). On a {kind['name'].lower()} that can mean people want something this is not, so the wording is not copied in. Use it only if it is true of what is sold."
        evidence["unverified"].append(f"Whether the page's product or service really is what the search names ({words}) has not been checked.")
    # A link count is not a reason to add links, and FAQ markup is not a growth lever by default. Neither makes a task of its own.
    for id_ in NOT_BY_COUNT:
        barred[id_] = "Not added: how many links a page has is not a reason to add more. Link suggestions come from the internal link tool, which checks that the two pages are related."

    # Order: the core parts, then every rule that fired (a prescription is a fact, not a hunch), then the extras.
    for id_ in CORE:
        if id_ in found and id_ not in barred and id_ not in NOT_DEFAULT:
            parts.append(_part(id_, found[id_], core=True))
    fired = [p["action_id"] for p in result["prescriptions"]]
    for id_ in fired:
        if id_ not in CORE and id_ not in barred:
            parts.append(_part(id_, found[id_], core=False))
    for id_ in EXTRAS:
        if id_ in found and id_ not in fired and id_ not in barred:
            parts.append(_part(id_, found[id_], core=False))
    for extra in extra_suggestions or []:
        parts.append(_part(extra["id"], extra, core=False))
    matched = _intent_match(search, intent, kind)
    # What the winners do that this page does not, only from pages that were read. A gap the comparison observed in
    # them becomes a part; one it only inferred is offered, not selected.
    inferred: list[dict[str, Any]] = []
    if winners_for and facts.get("outline"):
        asked = [] if "S-2" in barred else _questions_asked(signals, page_evidence, prompt)
        winners = winners_for(search, intent, chosen["url"], kind["name"], facts["outline"], asked)
        for n, gap in enumerate((winners.get("comparison") or {}).get("gaps") or [], start=1):
            (parts if gap["basis"] == "observed" else inferred).append(_gap_part(n, gap, read_intent))
    if matched:
        parts.insert(0, matched)

    # A core part with nothing from the page read can still be built from the topic's paired question.
    have = {p["id"] for p in parts}
    if "A-1" in barred:
        left_out.append({"id": "A-1", "name": PART_NAMES["A-1"], "reason": barred["A-1"]})
    elif "A-1" not in have and prompt:
        parts.insert(
            sum(1 for p in parts if p["id"] in _LEADS),
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
                "action_type": ACTION_TYPES["A-1"], "benefit": BENEFITS["A-1"][0], "benefit_why": BENEFITS["A-1"][1],
            },
        )
    elif "A-1" not in have:
        left_out.append({"id": "A-1", "name": PART_NAMES["A-1"], "reason": skipped.get("A-1", "No paired question for this topic.")})
    if "S-1" in barred:
        left_out.append({"id": "S-1", "name": PART_NAMES["S-1"], "reason": barred["S-1"]})
    elif "S-1" not in have:
        left_out.append({"id": "S-1", "name": PART_NAMES["S-1"], "reason": "The page's title and main heading already say the phrasing people search, or no longer phrasing shows for it."})
    if "P-1" in barred and "P-1" in found:
        left_out.append({"id": "P-1", "name": PART_NAMES["P-1"], "reason": barred["P-1"]})
    # Questions people ask about the term that the page does not answer, whether or not it already has an FAQ.
    # A rule that found an FAQ to mark up found an FAQ.
    has_faq = bool(facts.get("has_faq")) or "V-7" in found
    checked = ((winners or {}).get("comparison") or {}).get("questions")
    if checked and checked["missing"] and "S-2" not in barred:
        parts[:] = [p for p in parts if p["id"] != "S-2"]  # The questions that were checked replace a list that was not.
        idx = next((i for i, p in enumerate(parts) if p["id"] not in ("A-1", "S-1", *_LEADS)), len(parts))
        parts.insert(idx, _questions_part(checked, has_faq))
        have.add("S-2")
    if "S-2" not in have and has_faq and "S-2" not in barred:
        left_out.append({"id": "S-2", "name": PART_NAMES["S-2"], "reason": (
            f"The page already has an FAQ, and it answers all {checked['checked']} of the questions found for this search." if checked
            else "The page already has an FAQ. No question people ask about this search was found to check it against."
        )})
    elif "S-2" not in have and "V-7" not in have:
        if has_faq:
            left_out.append({"id": "S-2", "name": PART_NAMES["S-2"], "reason": barred["S-2"]})
        elif "S-2" in barred:
            left_out.append({"id": "S-2", "name": PART_NAMES["S-2"], "reason": barred["S-2"]})
        elif prompt:
            idx = next((i for i, p in enumerate(parts) if p["id"] not in ("A-1", "S-1", *_LEADS)), len(parts))
            parts.insert(
                idx,
                {
                    "id": "S-2", "name": PART_NAMES["S-2"], "core": True, "confirmed_by_rule": False,
                    "title": "Add a short FAQ",
                    "why": "No question-shaped search shows for the page, so the topic's paired question is the starting point. " + skipped.get("S-2", ""),
                    "steps": [
                        f"Start with the question customers ask AI platforms: “{prompt}”.",
                        "Add three to five questions a customer would ask before buying, each answered in one to three sentences.",
                    ],
                    "evidence": [],
                    "action_type": ACTION_TYPES["S-2"], "benefit": BENEFITS["S-2"][0], "benefit_why": BENEFITS["S-2"][1],
                }
            )
        else:
            reason = skipped.get("S-2", "No question to base an FAQ on.")
            left_out.append({"id": "S-2", "name": PART_NAMES["S-2"], "reason": reason})

    seen = {p["id"] for p in parts}
    # Suggestions the page read produced that are not in the action: offered to add, never repeated elsewhere.
    optional = [_part(s["id"], s, core=False) for s in result["suggestions"] if s["id"] not in seen and s["id"] not in NOT_OFFERED and s["id"] not in barred]
    # The site's own FAQ page, when this page does not link to it: part of the FAQ work when there is some, offered otherwise.
    for id_ in NOT_BY_COUNT:
        if id_ in found:
            left_out.append({"id": id_, "name": PART_NAMES.get(id_) or found[id_].get("title") or id_, "reason": barred[id_]})
    optional.extend(inferred)
    # Markup for an FAQ the page already has: offered, never selected for the person.
    optional.extend(_part(id_, found[id_], core=False) for id_ in NOT_DEFAULT if id_ in found)
    faq_link = _faq_page_link(db, client, site, chosen["url"])
    if faq_link and "S-2" in seen:
        parts.insert(next(i for i, p in enumerate(parts) if p["id"] == "S-2") + 1, faq_link)
    elif faq_link:
        optional.append(faq_link)
    if read_intent and no_top_answer and (prompt or "A-1" in found):
        optional.insert(0, {
            "id": "PC-1", "name": "Add a brief clarification", "core": False, "confirmed_by_rule": False,
            "title": "Add a one or two sentence clarification, only if it helps a buyer",
            "why": "A short line that clears up what the product or service is can help someone deciding. It is not an answer to the whole question, and it does not go above the buying information.",
            "steps": ["Write one or two sentences in the page's existing description area.", "Say only what is true of what is sold.", "Do not move or push down the price, options or call to action."],
            "evidence": [], "action_type": "Clarify product or service positioning", "benefit": "Conversion", "benefit_why": "A buyer who understands what the product is decides faster.",
        })
    # With no results page read, the parts that depend on intent are held, not dropped: they are shown as they would be and
    # cannot be approved until the results page is read.
    held = [] if read_intent else [
        {**_part(id_, found[id_], core=id_ in CORE), "held": True, "held_reason": barred[id_]}
        for id_ in found if id_ in barred and id_ in INTENT_DEPENDENT
    ]
    return finish(parts, left_out, optional, mismatch=False, observations=result["observations"], held=held)


def _questions_asked(signals: dict[str, Any] | None, page_evidence: dict[str, Any] | None, prompt: str) -> list[dict[str, Any]]:
    """The questions people ask about the term, each with where it was seen: the results page's "People also ask",
    question-shaped searches this page shows for, and the watchlist keyword's paired AI prompt."""
    from app.services.target_signals import _is_question

    asked = [{"question": q, "source": "people_also_ask", "detail": None} for q in (signals or {}).get("questions") or []]
    for q in (page_evidence or {}).get("page_queries") or []:
        if _is_question(q.get("query") or ""):
            asked.append({"question": q["query"], "source": "search_console", "detail": f"{int(q.get('impressions') or 0):,} impressions"})
    if prompt:
        asked.append({"question": prompt, "source": "prompt", "detail": None})
    return asked


def _questions_part(checked: dict[str, Any], has_faq: bool) -> dict[str, Any]:
    """The FAQ part, built from questions that were found for the term and checked against the page."""
    missing = checked["missing"]
    n = len(missing)
    steps = []
    for q in missing:
        seen_in = q["source_name"] + (f" ({q['detail']})" if q.get("detail") and q["source"] == "search_console" else f": {q['detail']}" if q.get("detail") else "")
        steps.append(f"“{q['question']}” Seen in: {seen_in}." + (f" {q['why']}" if q.get("why") else ""))
    steps.append("Answer each in one to three sentences, in the words you would use to a customer, using only facts already true of this page.")
    # No markup step: FAQ markup is not a default lever. Where a page's existing FAQ has markup, keeping the two in step is noted.
    steps.append("Add them to the page's existing FAQ. If that FAQ has markup, add them there too so the two stay in step." if has_faq else "Put them in a short FAQ section on the page.")
    sources = list(dict.fromkeys(q["source_name"] for q in missing))
    return {
        "id": "S-2", "name": "Add the missing questions to the FAQ" if has_faq else PART_NAMES["S-2"], "core": True, "confirmed_by_rule": False,
        "title": f"Add {n} missing question{'s' if n != 1 else ''} to the page's FAQ" if has_faq else f"Add a short FAQ with {n} question{'s' if n != 1 else ''} people ask",
        "why": (
            f"{checked['checked']} questions people ask about this search were checked against the page, and it does not answer {'this one' if n == 1 else f'these {n}'}. "
            + ("The page has an FAQ already, so they are added to it." if has_faq else "The page has no FAQ.")
            + " Which questions are missing is a model's reading of the page, not a rule: check each before writing."
        ),
        "steps": steps,
        "evidence": [f"{checked['checked']} questions checked, {n} not answered on the page", "Where the missing ones were seen: " + "; ".join(sources)],
        "action_type": ACTION_TYPES["S-2"], "benefit": BENEFITS["S-2"][0], "benefit_why": BENEFITS["S-2"][1],
    }


_FAQ_PAGE = re.compile(r"(^|[/\-_])(faqs?|frequently[-_]asked[-_]questions)([/\-_.]|$)", re.I)
_FAQ_TITLE = re.compile(r"\b(faqs?|frequently asked questions)\b", re.I)


def _faq_page_link(db: Session, client: Client, site: dict[str, str] | None, page: str) -> dict[str, Any] | None:
    """A part that links this page to the site's FAQ page, when the crawl holds one and no in-content link to it from this page.

    The FAQ page is one whose address says so; a title alone is not enough, since articles are often titled as FAQs.
    """
    from urllib.parse import urlsplit

    if not site:
        return None
    found = sorted((u for u, title in site.items() if u != page and _FAQ_PAGE.search(urlsplit(u).path) and (_FAQ_TITLE.search(title or "") or not title)), key=len)
    if not found:
        return None
    target = found[0]
    linked = db.query(FactCrawlInternalLink.id).filter(
        FactCrawlInternalLink.client_id == client.id, FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY,
        FactCrawlInternalLink.from_url == page, FactCrawlInternalLink.to_url == target, FactCrawlInternalLink.in_content.is_(True),
    ).first()
    if linked:
        return None
    return {
        "id": "FQ-1", "name": "Link to the site's FAQ page", "core": False, "confirmed_by_rule": False,
        "title": "Link to the site's FAQ page",
        "why": "The site has an FAQ page, and the crawl found no link to it in this page's content. Someone with a question this page does not answer has nowhere to go from here.",
        "steps": [f"The FAQ page: {target}", "Link to it from this page's FAQ, or from the point where a reader is most likely to have a further question.", "Use link text that says what is there, such as “See all frequently asked questions”."],
        "evidence": [f"FAQ page in the site crawl: {target}", "No in-content link from this page to it in the crawl."],
        "action_type": "Improve internal linking", "benefit": "SEO", "benefit_why": "A link from a page on the topic helps both a reader and a search engine reach the questions answered elsewhere on the site.",
    }


def _opening_text(result: dict[str, Any]) -> str | None:
    facts = result.get("page_facts") or {}
    return facts.get("h1")


def draft(bundle: dict[str, Any], month: str) -> dict[str, Any]:
    """The bundle as the task body: one title, the reasons, and every part's steps as a checklist."""
    parts = bundle["parts"]
    chosen = bundle["chosen"]
    ctx = bundle.get("context") or {}
    path = bundle["page"].split("//", 1)[-1].split("/", 1)[-1]
    investigation = any(p["id"] == "TI-1" for p in parts)
    steps: list[str] = []
    for i, p in enumerate(parts, start=1):
        steps.append(f"# {i}. {p['name']}")
        steps.extend(p["steps"])
    evidence = [f"{chosen['impressions']:,} impressions for searches containing “{bundle['keyword']}”, best position {chosen['position']}"]
    for p in parts:
        evidence.extend(f"{p['name']}: {line}" for line in p["evidence"])
        # Where the change lands, when it is anything but an ordinary edit to this one page.
        if p.get("scope") and (p["scope"] != ac.PAGE_SPECIFIC or p.get("note", "").startswith(("Use this page's own", "Template constraint unverified"))):
            evidence.append(f"{p['name']}: {p['scope']}. {p['note']}")
    if ctx:
        evidence.append(serp_intent.describe(ctx["intent"]))
        evidence.append(f"Page type: {ctx['page_type']['name']}. Fit with the search: {ctx['fit']['level']}.")
        need = ctx["intent"].get("consumer_need")
        if need:
            evidence.append(f"Consumer need ({need['basis']}): {need['name']}. {need['evidence']}")
        evidence.append(f"Crawl status: {ctx['evidence']['crawl_status_name']}. {ctx['evidence']['summary']}")
        evidence.extend(f"Unverified: {line}" for line in ctx["evidence"]["unverified"])
    names = ", ".join(p["name"].lower() for p in parts)
    if investigation:
        title = f"Investigate crawler access: /{path}"
        why = f"Our reader could not fetch this page, so nothing on it was judged. {parts[0]['why']}"
        done_when = "It is known whether the block affects search engines, and our reader can fetch the page or the reason it cannot is recorded."
        metric = "Whether the page is read on the next site crawl, and what Search Console's URL Inspection reports for it"
    else:
        title = f"Growth action: /{path} for “{bundle['keyword']}”"
        why = (
            f"This page gets the most impressions for “{bundle['keyword']}” ({chosen['impressions']:,} over three months). "
            f"The work is {len(parts)} part{'s' if len(parts) != 1 else ''}, done together on this one page: {names}."
        )
        done_when = "Every part above is live on the page."
        metric = f"Clicks and impressions for searches containing “{bundle['keyword']}” in Search Console, and whether the AI platforms cite the page in next month's LLM visibility run"
    return {
        "month": month,
        "kind": "growth_action",
        "rule_id": "GA",
        "search": bundle["keyword"],
        "page": bundle["page"],
        "title": title,
        "why": why,
        "steps": steps,
        "done_when": done_when,
        "metric": metric,
        "evidence": evidence,
    }
