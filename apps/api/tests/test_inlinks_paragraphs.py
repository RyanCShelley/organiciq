"""Internal links between pages that are about the same thing, with the paragraph the link belongs in.

The old suggester paired two pages when they were alike OR ranked for the same search, compared them on titles and
headings only, let a contact page be a source, and named no place for the link. Each of those is a test below.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from app.decisions import action_context as ac
from app.ingestion.crawler import pipeline
from app.ingestion.crawler.parse import MAX_PARAGRAPHS, parse_page
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot, PageParagraphVector
from app.services import inlinks, paragraph_vectors
from tests.test_inlinks import BASE, CRAWL, gsc, link

SUN, SOAP, MIX = [1.0, 0.05], [0.05, 1.0], [0.7, 0.7]


def vec(text: str):
    t = text.lower()
    v = np.array(SUN if ("sunscreen" in t or "spf" in t or "zinc" in t) and "soap" not in t else SOAP if "soap" in t else MIX, dtype="float32")
    return v / np.linalg.norm(v)


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    """Text about sunscreen is alike, text about soap is alike, and the two are not. No model is loaded."""
    inlinks._VECTORS.clear()
    monkeypatch.setattr(paragraph_vectors, "DIMENSIONS", 2)
    # In this two-number model, text about neither subject is 0.74 alike to sunscreen. The anchor floor sits above that here.
    monkeypatch.setattr(inlinks, "ANCHOR_MIN", 0.8)
    monkeypatch.setattr(inlinks.keyword_matcher, "embed_pages", lambda pages: np.array([vec(p.title or "") for p in pages]))
    monkeypatch.setattr(inlinks.keyword_matcher, "page_text", lambda p: p.title or "")
    monkeypatch.setattr(inlinks.keyword_matcher, "_embed", lambda texts: np.array([vec(t) for t in texts]))


def page(db, client, path, title, paragraphs=None, kind=None, words=400):
    url = BASE + path
    db.add(FactCrawlPageSnapshot(client_id=client.id, source=CRAWL_SOURCE_FIRST_PARTY, snapshot_date=CRAWL, raw_url=url, normalized_url=url, indexable=True, status_code=200,
                                 title=title, word_count=words, page_type=kind,
                                 paragraphs=[t if isinstance(t, dict) else {"heading": "", "text": t} for t in paragraphs] if paragraphs is not None else None))
    return url


TARGET = "/products/spf-30"
P_ANCHOR = "For everyday wear we reach for an SPF 30 sunscreen made with zinc oxide, because it suits sensitive skin."
P_PLAIN = "Sunscreen should go on fifteen minutes before you head outside, and again after swimming."


def site(db, client):
    page(db, client, TARGET, "SPF 30 Mineral Sunscreen | Shop Example", ["Our SPF 30 mineral sunscreen is reef safe and made with zinc oxide for the whole family."])
    page(db, client, "/blog/best-sunscreen", "The Best Natural Sunscreen for Kids | Shop Example", [P_PLAIN, P_ANCHOR, "Our soap is made in small batches by hand every week."])
    page(db, client, "/products/spf-50", "SPF 50 Sunscreen | Shop Example", ["This SPF 50 sunscreen is our strongest zinc formula for long days at the beach."])
    page(db, client, "/blog/soap-guide", "A Guide to Natural Soap | Shop Example", ["Natural soap is gentle on the skin and lasts longer when it is kept dry between uses."])
    page(db, client, "/pages/contact", "Contact us about sunscreen | Shop Example", ["Ask us anything about our sunscreen range and we will reply within one working day."])
    page(db, client, "/pages/about", "About our sunscreen company | Shop Example", ["We started making sunscreen in a small kitchen and now ship it to families everywhere."])
    gsc(db, client, "spf 30 sunscreen", TARGET, 900, 12, 6.0)
    gsc(db, client, "best natural sunscreen", "/blog/best-sunscreen", 3000, 200, 2.0)
    gsc(db, client, "spf 50", "/products/spf-50", 800, 200, 3.0)
    # The soap guide ranks for the target's own search, and is about something else.
    gsc(db, client, "spf 30 sunscreen", "/blog/soap-guide", 500, 150, 9.0)
    gsc(db, client, "contact", "/pages/contact", 500, 300, 1.0)
    gsc(db, client, "about", "/pages/about", 500, 300, 1.0)
    for path in ("/blog/best-sunscreen", "/products/spf-50", "/blog/soap-guide", "/pages/contact", "/pages/about"):
        for n in range(5):
            link(db, client, f"/other-{n}", path)
    db.commit()


def suggestions(db, client):
    out = inlinks._build(db, client, None, inlinks.states(db, client))
    return out, {s["source_url"]: s for s in next(t for t in out["targets"] if t["target_url"] == BASE + TARGET)["suggestions"]}


def test_a_shared_search_does_not_let_an_unrelated_page_through(db, client_a):
    site(db, client_a)
    out, by = suggestions(db, client_a)
    assert BASE + "/blog/soap-guide" not in by, "it ranks for the same search and is about soap: similarity is the requirement, the search only adds"
    assert "never qualifies it" in out["rule"] and out["body_text"] == {"sources": 4, "with_paragraphs": 4}, "the four pages read for their subject; the contact and about pages are not among them"


def test_contact_about_and_utility_pages_are_never_sources_and_blog_posts_lead(db, client_a):
    site(db, client_a)
    _, by = suggestions(db, client_a)
    assert set(by) == {BASE + "/blog/best-sunscreen", BASE + "/products/spf-50"}, "the contact and about pages are about sunscreen too, and are not read for it"
    assert list(by)[0] == BASE + "/blog/best-sunscreen" and by[BASE + "/blog/best-sunscreen"]["source_type"] == "Blog or article"
    assert any("written to be read" in r for r in by[BASE + "/blog/best-sunscreen"]["reasons"])


def test_each_suggestion_shows_the_paragraph_and_the_phrase_in_it_to_link(db, client_a):
    site(db, client_a)
    _, by = suggestions(db, client_a)
    blog = by[BASE + "/blog/best-sunscreen"]
    assert blog["paragraph"]["text"] == P_ANCHOR, "of two paragraphs equally close to the target, the one that already holds an anchor"
    assert blog["anchor_in_paragraph"] == "SPF 30 sunscreen" and blog["suggested_anchor"] == "SPF 30 sunscreen" and blog["anchor_type"] == "in_paragraph"
    assert any("already says “SPF 30 sunscreen”" in r for r in blog["reasons"])
    other = by[BASE + "/products/spf-50"]
    assert other["paragraph"]["text"].startswith("This SPF 50 sunscreen")
    assert "zinc" in other["anchor_in_paragraph"] and "50" not in other["anchor_in_paragraph"], "a phrase that means the target, where the old word match found none; never the SPF 50, which is another product"
    assert "never where a link goes" in _["rule"]


def test_a_crawl_without_paragraphs_still_works_on_titles_and_says_so(db, client_a):
    page(db, client_a, TARGET, "SPF 30 Mineral Sunscreen | Shop Example")
    page(db, client_a, "/blog/best-sunscreen", "The Best Natural Sunscreen for Kids | Shop Example")
    page(db, client_a, "/blog/soap-guide", "A Guide to Natural Soap | Shop Example")
    gsc(db, client_a, "spf 30 sunscreen", TARGET, 900, 12, 6.0)
    gsc(db, client_a, "best natural sunscreen", "/blog/best-sunscreen", 3000, 200, 2.0)
    db.commit()
    out, by = suggestions(db, client_a)
    assert by[BASE + "/blog/best-sunscreen"]["paragraph"] is None and out["body_text"]["with_paragraphs"] == 0
    assert "Crawl the site again" in out["rule"]


def choices(text, phrases, **kw):
    embed = lambda texts: np.array([vec(t) for t in texts])  # noqa: E731
    return [c for c, _ in inlinks.anchor_choices(text, phrases, embed([inlinks._key(x) for x in phrases]), embed, **kw)]


def test_the_anchor_is_chosen_by_meaning_and_follows_the_anchor_text_rules():
    text = "Our mineral sunscreen uses non-nano zinc oxide, and a reef-safe sunscreen matters when you swim. Read more here about soap."
    found = choices(text, ["Reef Safe Sunscreen", "best reef safe sunscreen for kids"])
    assert found[0] == "reef-safe sunscreen", "the target's own name, found as the paragraph writes it, comes first"
    assert "non-nano zinc oxide" in found, "a phrase that shares no word with the target's name and means the same thing"
    assert all(len(c.replace("-", " ").split()) <= 5 for c in found) and "mineral sunscreen uses non-nano zinc oxide" not in found, "an anchor is short"
    assert not any(c.lower().startswith(("our ", "a ", "and ")) or c.lower().endswith((" uses", " and", " when")) for c in found), "it stands on its own"
    assert not any("zinc oxide, and" in c or "swim. Read" in c for c in found), "it does not run across a comma or a full stop"
    assert not any("read more" in c.lower() or c.lower() == "more here" for c in found), "a generic label says nothing about where the link leads"
    assert "Shop Example" not in choices("We trust Shop Example sunscreen every day.", ["Shop Example Sunscreen"], brand=["shop example"]), "the brand alone could link anywhere"
    assert not any("50" in c for c in choices("Our SPF 50 sunscreen and zinc oxide stick last all day.", ["SPF 30 Sunscreen"])), "a phrase naming a number the target does not is another product"
    assert choices("Our Zinc Oxide Stick is small enough for a pocket.", ["mineral sunscreen"], own="Zinc Oxide Stick") == [], "the name of the page the paragraph is on does not link elsewhere"
    assert not any("'" in c.split()[-1] or "I've" in c for c in choices("The zinc sunscreen I've used and the sunscreen's cap.", ["mineral sunscreen"])), "a contraction or a possessive ending is mid-sentence"
    assert "sunscreen is our strongest" not in choices("This sunscreen is our strongest zinc formula yet.", ["SPF 30 Sunscreen"]), "a piece of a sentence is not a name"
    assert "zinc oxide sunscreen" not in choices("We make a zinc oxide sunscreen for children here.", ["mineral sunscreen"], links=["zinc oxide"]), "words that are already a link are not linked again"
    assert choices("Natural soap lasts longer when it is kept dry.", ["SPF 30 Sunscreen"]) == [], "nothing in the paragraph means the target"
    assert inlinks._is_list("Aloe juice, xanthan gum, eucalyptus oil, tea tree oil, green tea extract, vitamin E, citric acid") and not inlinks._is_list(text)


REVIEW = {"heading": "Pairs well with", "text": "Best SPF 30 sunscreen I have ever used, the zinc oxide never stings my eyes.", "review": True}
OLD_REVIEW = {"heading": "Customer Reviews", "text": "This SPF 30 sunscreen is the only zinc oxide one my kids will wear."}


def test_a_review_is_never_where_a_link_goes_and_a_page_of_only_reviews_is_not_a_source(db, client_a):
    page(db, client_a, TARGET, "SPF 30 Mineral Sunscreen | Shop Example", ["Our SPF 30 mineral sunscreen is reef safe and made with zinc oxide for the whole family."])
    page(db, client_a, "/products/spf-50", "SPF 50 Sunscreen | Shop Example", [REVIEW, OLD_REVIEW, "A sunscreen stick for long days at the beach and by the pool."])
    page(db, client_a, "/pages/testimonials", "Sunscreen testimonials | Shop Example", [REVIEW, OLD_REVIEW])
    page(db, client_a, "/blog/soap-guide", "A Guide to Natural Soap | Shop Example", ["Natural soap is gentle on the skin and lasts longer when it is kept dry between uses."])
    gsc(db, client_a, "spf 30 sunscreen", TARGET, 900, 12, 6.0)
    gsc(db, client_a, "spf 50", "/products/spf-50", 800, 200, 3.0)
    gsc(db, client_a, "sunscreen reviews", "/pages/testimonials", 800, 200, 3.0)
    db.commit()
    _, by = suggestions(db, client_a)
    assert set(by) == {BASE + "/products/spf-50"}, "the testimonials page is about sunscreen and has no sentence of the site's own"
    assert by[BASE + "/products/spf-50"]["paragraph"]["text"].startswith("A sunscreen stick"), "both reviews name the target outright, and neither is used: marked by the crawl, or under a reviews heading in an older one"


def test_two_links_to_one_page_do_not_carry_the_same_words_when_the_paragraph_offers_another(db, client_a):
    page(db, client_a, TARGET, "SPF 30 Mineral Sunscreen | Shop Example", ["Our SPF 30 mineral sunscreen is reef safe and made with zinc oxide for the whole family."])
    page(db, client_a, "/blog/one", "Sunscreen for the beach | Shop Example", ["Pack a mineral sunscreen made with zinc oxide for the beach."])
    page(db, client_a, "/blog/two", "Sunscreen for the pool | Shop Example", ["Pack a mineral sunscreen made with zinc oxide for the pool."])
    gsc(db, client_a, "mineral sunscreen", TARGET, 900, 12, 6.0)
    gsc(db, client_a, "beach sunscreen", "/blog/one", 800, 200, 3.0)
    gsc(db, client_a, "pool sunscreen", "/blog/two", 800, 100, 3.0)
    db.commit()
    _, by = suggestions(db, client_a)
    anchors = [s["anchor_in_paragraph"] for s in by.values()]
    assert len(anchors) == 2 and anchors[0] == "mineral sunscreen" and anchors[1] and anchors[1] != anchors[0]


def test_a_paragraph_is_embedded_once_and_unused_vectors_go_after_a_crawl(db, client_a):
    calls: list[int] = []

    def embed(texts):
        calls.append(len(texts))
        return np.array([vec(t) for t in texts])

    first = paragraph_vectors.ensure(db, client_a.id, ["Sunscreen for the beach.", "sunscreen  for the BEACH.", "Soap for the bath."], embed)
    again = paragraph_vectors.ensure(db, client_a.id, ["Sunscreen for the beach.", "Soap for the bath."], embed)
    assert calls == [2] and set(first) == set(again) and db.query(PageParagraphVector).count() == 2, "the same text is one vector, worked out once"
    assert paragraph_vectors.prune(db, client_a.id, {paragraph_vectors.text_hash("Soap for the bath.")}) == 1
    assert db.query(PageParagraphVector).count() == 1


def test_the_crawl_keeps_body_paragraphs_and_leaves_out_menus_footers_and_short_lines():
    body = (
        "<html><head><title>T</title></head><body><nav><p>Menu item one two three four five six seven eight nine</p></nav>"
        "<h1>Natural Sunscreen</h1><p>Short one.</p><p>Our mineral sunscreen uses non-nano zinc oxide and is safe for reefs and for sensitive skin.</p>"
        "<h2>How to apply</h2><ul><li>Apply generously fifteen minutes before going out in the sun every day.</li><li>Reapply</li></ul>"
        "<aside><p>Sign up for our newsletter to get ten percent off your first order today.</p></aside>"
        "<footer><p>Footer text that is long enough to count as a paragraph in principle here.</p></footer>"
        + "".join(f"<p>Paragraph number {n} has more than eight words in it for the test.</p>" for n in range(80)) + "</body></html>"
    )
    found = parse_page(url="https://x/p", body=body).paragraphs
    assert found[0] == {"heading": "Natural Sunscreen", "text": "Our mineral sunscreen uses non-nano zinc oxide and is safe for reefs and for sensitive skin."}
    assert found[1] == {"heading": "How to apply", "text": "Apply generously fifteen minutes before going out in the sun every day."}
    assert len(found) == MAX_PARAGRAPHS and not any("Menu" in p["text"] or "Footer" in p["text"] or "newsletter" in p["text"] for p in found)


def test_a_changed_page_is_dated_and_keeps_what_it_replaced_for_thirty_days():
    today = date(2026, 11, 17)
    old_text, new_text = [{"heading": "", "text": "The old wording of the page."}], [{"heading": "", "text": "The new wording of the page."}]

    def row(paragraphs):
        return {"normalized_url": "u", "paragraphs": paragraphs, "content_hash": pipeline.content_hash(paragraphs)}

    def before(paragraphs, **kw):
        return {"u": SimpleNamespace(content_hash=pipeline.content_hash(paragraphs), paragraphs=paragraphs, content_changed_on=None, previous_paragraphs=None, previous_replaced_on=None, **{}) if not kw else
                SimpleNamespace(**{"content_hash": pipeline.content_hash(paragraphs), "paragraphs": paragraphs, "content_changed_on": None, "previous_paragraphs": None, "previous_replaced_on": None, **kw})}

    changed = row(new_text)
    pipeline.carry_changes([changed], before(old_text), today=today)
    assert changed["content_changed_on"] == today and changed["previous_paragraphs"] == old_text and changed["previous_replaced_on"] == today

    same = row(new_text)
    pipeline.carry_changes([same], before(new_text, content_changed_on=today - timedelta(days=10), previous_paragraphs=old_text, previous_replaced_on=today - timedelta(days=10)), today=today)
    assert same["content_changed_on"] == today - timedelta(days=10) and same["previous_paragraphs"] == old_text, "unchanged: the date and the earlier version stand"

    aged = row(new_text)
    pipeline.carry_changes([aged], before(new_text, content_changed_on=today - timedelta(days=40), previous_paragraphs=old_text, previous_replaced_on=today - timedelta(days=40)), today=today)
    assert aged["content_changed_on"] == today - timedelta(days=40) and aged["previous_paragraphs"] is None, "the earlier version is dropped after 30 days; the date is kept"

    unread = row(None)
    pipeline.carry_changes([unread], before(old_text), today=today)
    assert unread["paragraphs"] == old_text and unread["content_changed_on"] is None, "a page that could not be read has not changed"

    new = row(new_text)
    pipeline.carry_changes([new], {}, today=today)
    assert new["content_changed_on"] is None, "a page seen for the first time has no change to report"


def test_every_page_gets_a_type_including_contact_and_utility_pages():
    kinds = {u: ac.classify_page("https://x" + u)["type"] for u in ("/contact", "/pages/contact-us", "/policies/privacy-policy", "/cart", "/about.html", "/blogs/news/shipping-tips", "/products/returns-kit", "/collections/spf", "/")}
    assert kinds == {"/contact": "contact", "/pages/contact-us": "contact", "/policies/privacy-policy": "utility", "/cart": "utility", "/about.html": "about",
                     "/blogs/news/shipping-tips": "article", "/products/returns-kit": "product", "/collections/spf": "category", "/": "homepage"}


def test_the_crawl_marks_what_customers_wrote_and_the_words_that_are_already_links():
    body = (
        "<html><head><title>T</title></head><body class='template-product has-reviews'><h1>Aloe Gel</h1>"
        "<p>Our aloe gel cools the skin after sun, and pairs with our <a href='/products/lotion'>rose hip lotion</a> for dry days.</p>"
        "<div class='jdgm-widget jdgm-review-widget'><div class='jdgm-rev__body'><p>Best product for sun burn! Been using it for twenty years now.</p></div></div>"
        "<div class='product-preview'><p>A preview of the gel in its new bottle, coming to the shop this summer.</p></div>"
        "<div itemprop='review' itemscope><p>My family has used this gel for more than ten years to soothe skin.</p></div>"
        "<h2>What our customers say</h2><p>Found this while on holiday and now we keep it on hand all summer.</p>"
        "</body></html>"
    )
    found = {p["text"][:12]: p for p in parse_page(url="https://x/p", body=body).paragraphs}
    assert found["Our aloe gel"].get("links") == ["rose hip lotion"] and "review" not in found["Our aloe gel"], "a class on the body describes the page, not this paragraph"
    assert found["Best product"]["review"] and found["My family ha"]["review"] and found["Found this w"]["review"], "a review app's block, review markup, and a reviews heading"
    assert "review" not in found["A preview of"], "a preview is not a review"


def test_a_sentence_is_written_for_the_link_checked_and_kept_for_the_whole_team(db, client_a):
    site(db, client_a)
    t, s = BASE + TARGET, BASE + "/products/spf-50"
    answers = iter(['{"sentence": "Try our SPF 30 sunscreen, proven to block 99% of rays."}', '{"sentence": "For everyday wear, our lighter SPF 30 sunscreen is the one to reach for."}'])
    prompts: list[str] = []

    def ask(prompt):
        prompts.append(prompt)
        return next(answers)

    out = inlinks.write_sentence(db, client_a, s, t, "SPF 30 sunscreen", "a@b.c", ask)
    assert out == {"ok": True, "sentence": "For everyday wear, our lighter SPF 30 sunscreen is the one to reach for.", "anchor": "SPF 30 sunscreen"}
    assert len(prompts) == 2 and "refused because" in prompts[1] and "99%" in prompts[1], "the first try stated a number the paragraph does not, and was sent back with the reason"
    assert "This SPF 50 sunscreen is our strongest zinc formula" in prompts[0] and '"SPF 30 sunscreen"' in prompts[0]
    _, by = suggestions(db, client_a)
    assert by[s]["sentence"] == out["sentence"] and by[s]["sentence_anchor"] == "SPF 30 sunscreen" and by[s]["status"] == "todo", "anyone opening the page sees the same sentence"
    inlinks.set_state(db, client_a, s, t, "a@b.c", anchor="mineral sunscreen")
    assert suggestions(db, client_a)[1][s]["sentence"] is None, "other link text, so the sentence written around the old words goes"


def test_a_sentence_that_breaks_the_rules_is_never_saved():
    para = "This SPF 50 sunscreen is our strongest zinc formula for long days at the beach."
    ok = lambda text: inlinks.sentence_problem(text, "mineral sunscreen", para + " SPF 30 Mineral Sunscreen")  # noqa: E731
    assert ok("For shorter days, our lighter mineral sunscreen is easier to wear.") is None
    assert "exactly once" in ok("For shorter days, our lighter sunscreen is easier to wear.")
    assert "exactly once" in ok("Our mineral sunscreen is a mineral sunscreen for every day.")
    assert "one sentence" in ok("Try a mineral sunscreen. It is lighter.")
    assert "which the paragraph does not" in ok("Our mineral sunscreen blocks 99% of rays on long days.")
    assert ok("Our SPF 30 mineral sunscreen is lighter for short days.") is None, "a number in the target's name is the target's own"
    assert "claim" in ok("Our mineral sunscreen is clinically shown to be gentle.")
    assert "markup" in ok("See our mineral sunscreen at https://shop.example/spf-30.")
    assert "limit" in ok("Our mineral sunscreen " + "is very " * 30 + "light.")


def test_no_sentence_is_written_without_a_paragraph_a_real_link_text_or_a_suggested_link(db, client_a):
    site(db, client_a)
    never = lambda prompt: (_ for _ in ()).throw(AssertionError("the model is not asked"))  # noqa: E731
    t = BASE + TARGET
    assert "no longer suggested" in inlinks.write_sentence(db, client_a, BASE + "/blog/soap-guide", t, "SPF 30 sunscreen", "a@b.c", never)["reason"]
    assert "says where the link leads" in inlinks.write_sentence(db, client_a, BASE + "/products/spf-50", t, "read more here", "a@b.c", never)["reason"]


def test_link_text_keeps_the_capitals_the_page_writes():
    from app.inlink_tools.anchors import _title_case

    assert _title_case("FSA/HSA Eligible Products for Kids") == "FSA/HSA Eligible Products for Kids"
    assert _title_case("SPF 30 mineral sunscreen for iPhone users") == "SPF 30 Mineral Sunscreen for iPhone Users"
    assert _title_case("ZOEY NATURALS BUBBLE BATHS") == "Zoey Naturals Bubble Baths", "a title all in capitals is still brought down"
    assert _title_case("seo tips") == "SEO Tips"
    from app.inlink_tools.anchors import build_candidates

    made = build_candidates("https://shop.example/collections/fsa-hsa-kids", "FSA/HSA Eligible Products for Kids")
    assert made["partial_match"][0] == "FSA/HSA Eligible Products for Kids" and made["branded"][0].endswith("FSA/HSA Eligible Products for Kids")
