"""Things worth doing that the catalog's rules cannot yet confirm.

The catalog's Visibility rules are strict on purpose: each fires only when the data that proves
it is present (a declared owner page, the SERP's features, the site-wide link crawl). For a page
read on demand most of that data is absent, so most pages return "no rule fires", which is true
and not very useful.

This layer says what is still worth looking at, using only what a page read and Search Console
do know. Every item is labeled *unconfirmed* and names the missing data that would turn it into
a rule. Nothing here is a prescription, nothing is sent to the plan, and the catalog is untouched,
so the live tool's rules do not change.

Suggestions never invent copy. They quote what the page says now and what people search, and
leave the wording to a person.
"""

from __future__ import annotations

from typing import Any

from app.decisions.catalog import PageFacts, _mentions
from app.decisions.ctr_curve import expected_ctr_percent
from app.ingestion.crawler.parse import ParsedPage
from app.services.target_signals import _is_question

#: A form with this many fields or more counts as long.
FRICTION_FORM_FIELDS = 6

_STOP = frozenset("a an and are as at be by for from how in is it of on or the to what when where which who why with your".split())


def _tokens(text: str) -> set[str]:
    import re

    return {t for t in re.findall(r"[^\W_]+", text.lower()) if len(t) >= 2 and t not in _STOP}


def _item(id_: str, title: str, why: str, steps: list[str], needs: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": id_,
        "title": title,
        "why": why,
        "steps": steps,
        "needs_to_confirm": needs,
        "confidence": "unconfirmed",
        "evidence": evidence or [],
    }


def _opening(parsed: ParsedPage) -> str:
    """The page's first headed passage as it reads now: the main heading and the paragraph under it."""
    first = next((sec for sec in parsed.sections if sec.first_paragraph.strip()), None)
    paragraph = " ".join(first.first_paragraph.split())[:240] if first else ""
    return f"Main heading: “{parsed.h1 or '(none)'}”." + (f" The first paragraph reads: “{paragraph.rstrip('.')}”." if paragraph else " No opening paragraph was found.")


def _answer_item(search: str, parsed: ParsedPage, llm: dict[str, Any]) -> dict[str, Any] | None:
    """A-1: the platforms answered the paired question and did not all cite this site."""
    platforms = llm["platforms"]
    missed = [p["platform"] for p in platforms if not p["cited"]]
    if not missed:
        return None
    cited = [p["platform"] for p in platforms if p["cited"]]
    named = llm["named"]
    why = (
        f"On {llm['run_date']}, {', '.join(missed)} answered “{llm['prompt']}” without citing this site"
        + (f" ({', '.join(cited)} did cite it)" if cited else "")
        + (f", and named {', '.join(named[:4])} instead" if named else "")
        + ". A page that opens with a direct, factual answer to the question is easier for them to quote."
    )
    return _item(
        "A-1",
        f"Answer “{llm['prompt']}” at the top of the page",
        why,
        [
            f"The question the platforms were asked: “{llm['prompt']}” (paired with the watchlist keyword “{llm['keyword']}”).",
            _opening(parsed),
            "Write a two to three sentence answer to that question, in plain words a customer would use, and put it directly under the main heading.",
            "Use only facts already true of this page and product (what it is, who it suits, what it is made of, any certification). Do not claim anything the page does not already support.",
            "Next month's run asks the same question again: check whether a platform now cites this page.",
        ],
        "Which pages the platforms did cite for this question. Only whether this site was cited is stored, not the full source list.",
        [f"{p['platform']}: {'cited this site' if p['cited'] else 'did not cite this site'}" for p in platforms],
    )


def _opening_item(search: str, parsed: ParsedPage, why: str, evidence: list[str]) -> dict[str, Any]:
    """P-1: rewrite the page's opening so the first screen answers what the visitor came for."""
    return _item(
        "P-1",
        "Rewrite the opening so it answers what they came for",
        why,
        [
            f"Visitors arrive for “{search}”." if search else "Think of the search that brings visitors here.",
            _opening(parsed),
            "Rewrite the first two sentences to say, plainly, what this page is and how it answers that search. Lead with the answer or the product, not a brand story.",
            "Keep the words of the search where they read naturally, and keep it short enough to read without scrolling.",
        ],
        "Why they leave or do not click: the first screen as a visitor sees it, and the snippet. Neither is measured here.",
        evidence,
    )


def suggest(
    *,
    search: str,
    url: str,
    row: dict[str, Any],
    parsed: ParsedPage,
    facts: PageFacts,
    evidence: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """`{suggestions: [...], skipped: [{id, name, reason}]}`."""
    out: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    wanted = _tokens(search)
    page_queries = evidence.get("page_queries") or []

    # A-1: the AI platforms answered this search's paired prompt without citing the site.
    llm = evidence.get("llm")
    if llm and llm.get("ok"):
        answer = _answer_item(search, parsed, llm)
        if answer:
            out.append(answer)
        else:
            skipped.append({"id": "A-1", "name": "Answer the paired question at the top", "reason": f"Every platform cited this site for “{llm['prompt']}” in the run of {llm['run_date']}."})
    elif llm:
        skipped.append({"id": "A-1", "name": "Answer the paired question at the top", "reason": llm["reason"]})

    # S-6: more than one page shows for the search.
    competing = int(evidence.get("competing_pages") or 0)
    if competing > 1:
        out.append(
            _item(
                "S-6",
                f"Decide which page should own “{search}”",
                f"{competing} pages of the site show for this search, so they split its impressions and each ranks lower than one page might.",
                [
                    f"Pick the page that should rank for “{search}”.",
                    "Point the other pages at it with an in-content link, and stop repeating the same target phrase in their titles.",
                ],
                "Which page should own the search. This tool doesn't hold that yet.",
                [f"{competing} pages show for this search in Search Console"],
            )
        )

    # S-1: phrasing people search that the title and main heading do not use.
    brand = evidence.get("brand_keys") or []
    related = [
        q for q in page_queries
        if q["query"] != " ".join(search.lower().split())
        and not any(f" {k} " in f" {q['query'].lower()} " for k in brand)  # a brand search is navigation: no wording change moves it
        and len(_tokens(q["query"]) & wanted) >= min(2, len(wanted))
        and q["impressions"] >= 20
    ]
    missing = [q for q in related if not _mentions(q["query"], parsed.title) and not _mentions(q["query"], parsed.h1)][:3]
    if missing:
        slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1].replace("-", " ").lower()
        steps = [
            f"“{q['query']}”: {q['impressions']:,} impressions at position {q['position']}, in neither the title nor the main heading."
            for q in missing
        ]
        steps.append(f"Today the title reads “{parsed.title}” and the main heading “{parsed.h1}”.")
        steps.append("Work the closest natural phrasing into the title, and into the main heading if it reads well. Do not stuff it.")
        top = missing[0]["query"]
        in_slug = all(t in slug for t in _tokens(top))
        steps.append(
            f"The URL ({url.split('/')[-1]}) {'already carries' if in_slug else 'does not carry'} the words of “{top}”. "
            "Changing a live address needs a redirect, so treat the URL as a note and not a first move."
        )
        out.append(
            _item(
                "S-1",
                "Use the phrasing people actually search",
                "The page already ranks for these longer searches. Saying them in the title or heading is the cheapest way to line the page up with them.",
                steps,
                "A person's judgment that the wording reads naturally. No data is missing.",
                [f"Page queries from Search Console, {len(page_queries)} with impressions"],
            )
        )

    # S-5: top-three position, enough impressions, click-through under the benchmark.
    impressions, clicks, position = row["impressions"], row["clicks"], float(row["position"])
    if position <= 3.5 and impressions >= 100:
        actual = clicks / impressions * 100
        expected = expected_ctr_percent(position)
        if actual < 0.9 * expected:
            out.append(
                _item(
                    "S-5",
                    "Reread the title and description as the searcher",
                    f"Click-through is {actual:.1f}% against {expected:.1f}% expected at position {position:.1f}. At this position a gap is usually the snippet, not the ranking.",
                    [
                        f"Search “{search}” and read the result as a shopper would.",
                        f"Title now: “{parsed.title}”.",
                        f"Description now: “{parsed.description or '(none)'}”.",
                        "Ask whether they say this page is the answer, and what a competitor's snippet promises that this one does not.",
                    ],
                    "Whether SERP features (an AI answer, shopping results) sit above the result and take clicks that wording cannot win back. Not pulled yet.",
                    [f"{impressions:,} impressions, {clicks:,} clicks"],
                )
            )

    # P-1: ranks on the first page but click-through is under the benchmark (the top three are S-5's, the snippet).
    if 3.5 < position <= 10.5 and impressions >= 100:
        actual = clicks / impressions * 100
        expected = expected_ctr_percent(position)
        if actual < 0.9 * expected:
            out.append(
                _opening_item(
                    search,
                    parsed,
                    f"The page ranks at position {position:.1f}, but click-through is {actual:.1f}% against {expected:.1f}% expected there. A page that opens by answering the search earns more of the clicks it is already shown for.",
                    [f"{impressions:,} impressions, {clicks:,} clicks"],
                )
            )

    # S-3: nothing on the page an answer engine can lift whole.
    if facts.sections and not any(s.extractable for s in facts.sections):
        out.append(
            _item(
                "S-3",
                "Give an answer engine something to lift",
                f"None of the page's {len(facts.sections)} headed sections holds a table, a bulleted summary or a stat block, which are the shapes snippets and AI answers quote.",
                [
                    f"Near the top, add a short table or bulleted summary of what someone searching “{search}” wants to compare.",
                    "Keep it factual and true to the page, so what is lifted is accurate.",
                ],
                "The SERP's features for this search, to know whether a snippet or AI answer is being shown at all. Not pulled yet.",
                [f"{len(facts.sections)} sections read, none with a table, list or stat"],
            )
        )

    # S-2: an FAQ built from questions people really ask. (An existing FAQ without markup is V-7.)
    if not facts.has_faq_section:
        questions = [q for q in page_queries if _is_question(q["query"])][:5]
        if questions:
            out.append(
                _item(
                    "S-2",
                    "Add a short FAQ from real questions",
                    "The page has no FAQ, and it already gets impressions for questions people type.",
                    [f"“{q['query']}” ({q['impressions']:,} impressions)" for q in questions]
                    + [
                        "Answer each in one to three sentences on the page, in the words you would use to a customer.",
                        "Then mark the FAQ up as FAQPage so search engines can read it as questions and answers.",
                    ],
                    "Whether an AI answer or featured snippet appears for these questions. Not pulled yet.",
                    [f"{len(questions)} question-shaped searches for this page"],
                )
            )
        else:
            skipped.append(
                {
                    "id": "S-2",
                    "name": "Add a short FAQ",
                    "reason": "No question-shaped search shows for this page, so there is nothing real to base an FAQ on.",
                }
            )

    # S-4: other pages on the same topic that could link here.
    crawl = evidence.get("crawl")
    if crawl:
        donors = crawl["sources_without_link"]
        checked = f"Checked against the crawl of {crawl['date']}: these pages show for the topic and have no in-content link here."
        already = crawl["sources_already_linking"]
    else:
        donors = evidence.get("donors") or []
        checked = ""
        already = []
    if donors:
        out.append(
            _item(
                "S-4",
                "Link here from pages on the same topic",
                (
                    "These pages already show for searches on this topic, so a link from them is relevant and carries readers."
                    + (f" This page has {crawl['inbound']} in-content {'link' if crawl['inbound'] == 1 else 'links'} against a site median of {crawl['median']:g}, so this is optional, not a fix for a gap." if crawl and crawl["inbound"] >= crawl["median"] else "")
                ),
                [
                    f"{d['url']} (shows for “{d['query']}”, {d['impressions']:,} impressions): add an in-content link to this page where it reads naturally."
                    for d in donors[:3]
                ]
                + ([checked] if checked else ["Check each page does not already link here first."]),
                (
                    "Nothing more: the crawl has already checked that these do not link here."
                    if crawl
                    else "The site-wide link crawl, to see which of these already link here and how many links this page has against the site's median."
                ),
                [f"{len(donors)} topical pages without a link, from the crawl" if crawl else f"{len(donors)} topical pages found in Search Console"],
            )
        )
    else:
        skipped.append(
            {
                "id": "S-4",
                "name": "Add internal links",
                "reason": (
                    f"Every page on the topic that shows in Search Console already links here ({len(already)} checked against the crawl of {crawl['date']})."
                    if crawl and already
                    else "No other page shows for searches on this topic, so no natural source for a link was found."
                ),
            }
        )

    return {"suggestions": out, "skipped": skipped}


def suggest_traffic(*, lost: list[dict[str, Any]], unit: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """For a page whose organic sessions fell: which searches it lost, and whether rankings or demand moved."""
    out: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if not lost:
        skipped.append(
            {
                "id": "T-S1",
                "name": "Find the searches that lost the most",
                "reason": "No search with at least 20 impressions before lost clicks or impressions on this page, so the drop is not in the searches Search Console reports.",
            }
        )
        return {"suggestions": out, "skipped": skipped}

    def line(x: dict[str, Any]) -> str:
        pos = x["position"]
        moved = f", position {pos['previous']} to {pos['current']}" if pos["current"] is not None else ", no longer showing"
        return f"“{x['query']}”: {x['impressions']['previous']:,} to {x['impressions']['current']:,} impressions, {x['clicks']['previous']} to {x['clicks']['current']} clicks{moved}"

    out.append(
        _item(
            "T-S1",
            "Start with the searches that lost the most",
            "These are the searches on this page that lost the most clicks, three months against the three before.",
            [line(x) for x in lost[:5]] + ["Open each in Search Console and in the search results, and see what now ranks above the page."],
            "A person's read of the results. Nothing is missing, but the cause is not stated: this lists what fell, not why.",
            [f"{len(lost)} searches lost clicks or impressions"],
        )
    )

    slipped = [x for x in lost if x["position"]["current"] is None or x["position"]["current"] - x["position"]["previous"] >= 1.5]
    if len(slipped) >= max(2, round(len(lost) * 0.6)):
        out.append(
            _item(
                "T-S2",
                "Rankings fell, not just demand",
                f"{len(slipped)} of the {len(lost)} searches moved down the results or dropped out, so this looks like lost ranking, not fewer people searching.",
                ["Compare the page with what now outranks it for the biggest loser.", "Check the page was not changed, redirected or slowed in the period."],
                "A view of what changed on the page in that period. Not tracked: the crawl keeps one snapshot.",
                [f"{len(slipped)} searches with a worse position"],
            )
        )
    elif lost:
        out.append(
            _item(
                "T-S2",
                "Demand fell more than rankings",
                "Most of these searches kept their position but drew fewer impressions, which points to fewer people searching, not a ranking loss.",
                ["Compare the same months a year ago for a seasonal pattern before acting on the page."],
                "A year of Search Console history to separate a season from a decline.",
                [f"{len(lost) - len(slipped)} of {len(lost)} searches kept their position"],
            )
        )
    return {"suggestions": out, "skipped": skipped}


def suggest_leads(
    *, row: dict[str, Any] | None, site: dict[str, Any], path: dict[str, Any], parsed: ParsedPage, noun: str
) -> dict[str, list[dict[str, Any]]]:
    """For a page whose organic visitors convert or engage less than the site's own median."""
    out: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if row is None:
        return {"suggestions": out, "skipped": [{"id": "L-S1", "name": "Compare with the site", "reason": "This page is not among those the site's median is measured on (it needs 50 organic sessions over the three months)."}]}

    med_eng, med_conv = site.get("median_engagement_rate"), site.get("median_conversion_rate")
    article = "an" if noun["singular"][:1].lower() in "aeiou" else "a"
    ends = f"{row['conversion_rate']}% of sessions end in {article} {noun['singular']} here, against a site median of {med_conv}%."
    low_eng = med_eng is not None and row["engagement_rate"] < med_eng - 5
    low_conv = med_conv is not None and row["conversion_rate"] < med_conv

    if low_eng:
        out.append(
            _item(
                "L-S1",
                "Visitors leave without engaging",
                f"Engagement is {row['engagement_rate']}% against a site median of {med_eng}%. Many arrive and go straight back.",
                [
                    "Open the page as a visitor from the search that brings them: does the first screen say they are in the right place?",
                    f"The page has {parsed.word_count:,} words in {len(parsed.sections)} headed sections and {parsed.conversion_elements} conversion elements.",
                ],
                "Why they leave (speed, mismatch with the search, layout). Page-level behavior is not pulled.",
                [f"engagement {row['engagement_rate']}% vs site median {med_eng}%"],
            )
        )
    if low_conv:
        if path["declared"] == 0:
            out.append(
                _item(
                    "L-S2",
                    f"Check the way from this page to an {noun['singular']}",
                    f"{ends} The page has {parsed.conversion_elements} conversion elements on it.",
                    ["Look at where a visitor is meant to go next from this page, and how easy that is to find.",
                     "No conversion pages are declared for this client, so the path could not be checked against them. Declare them in Settings → Conversions & goals to check."],
                    "Declared conversion pages, to check the page links to them.",
                    [f"{row['conversions']} {noun['plural']} from {row['sessions']:,} sessions"],
                )
            )
        elif path["crawl"] and not path["linked_to"]:
            out.append(
                _item(
                    "L-S2",
                    f"This page does not link to a conversion page",
                    f"{ends} The crawl found no in-content link from here to any of the {path['declared']} conversion pages declared for this client.",
                    ["Add a clear in-content link, or a call to action, to the conversion page that fits what this visitor wants."],
                    "Nothing more: the crawl has already checked.",
                    [f"0 of {path['declared']} conversion pages linked from this page"],
                )
            )
        else:
            out.append(
                _item(
                    "L-S2",
                    f"Check the way from this page to an {noun['singular']}",
                    f"{ends} It links to {len(path['linked_to'])} of {path['declared']} declared conversion pages, so the link exists: the question is whether visitors act on it.",
                    ["Read the page as a visitor and ask whether the next step is the obvious one."],
                    "How visitors move after landing here. Not pulled.",
                    [f"{row['conversions']} {noun['plural']} from {row['sessions']:,} sessions"],
                )
            )
    if low_eng:
        out.append(
            _opening_item(
                "",
                parsed,
                f"Engagement is {row['engagement_rate']}% against a site median of {med_eng}%: many visitors leave without doing anything. The opening is the first thing they judge the page on.",
                [f"engagement {row['engagement_rate']}% vs site median {med_eng}%"],
            )
        )
    if low_conv:
        friction = []
        if parsed.conversion_elements == 0:
            friction.append("The page has no form, phone or email link, or button that asks for the next step.")
        if path.get("crawl") and path["declared"] and not path["linked_to"]:
            friction.append(f"It does not link in its content to any of the {path['declared']} declared conversion pages.")
        if parsed.form_fields >= FRICTION_FORM_FIELDS:
            friction.append(f"The form on the page asks for {parsed.form_fields} fields.")
        if parsed.contact_only_in_footer:
            friction.append("The only phone number or email link is in the footer.")
        if friction:
            out.append(
                _item(
                    "F-1",
                    f"Remove what stands between the visitor and the {noun['singular']}",
                    f"{ends} The page read shows: " + " ".join(friction),
                    friction
                    + [
                        "Fix the one that matches how a visitor would act: a shorter form, a call to action near the top, an in-content link to the page that converts.",
                        "Change one thing, so next month's numbers say which one mattered.",
                    ],
                    "How visitors behave on the page (where they stop). Page-level behavior is not pulled.",
                    [f"{row['conversions']} {noun['plural']} from {row['sessions']:,} sessions", f"{parsed.conversion_elements} conversion elements on the page"],
                )
            )
        else:
            skipped.append(
                {
                    "id": "F-1",
                    "name": "Remove friction",
                    "reason": "The page read found none of the known frictions: it has a conversion element, no long form, contact details outside the footer, and it links to a conversion page.",
                }
            )
    if not (low_eng or low_conv):
        skipped.append(
            {
                "id": "L-S1",
                "name": "Weak engagement or conversion",
                "reason": f"This page is at or above the site's median on both ({row['engagement_rate']}% engagement, {row['conversion_rate']}% conversion), so there is no gap to explain.",
            }
        )
    return {"suggestions": out, "skipped": skipped}
