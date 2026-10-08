"""What a page actually says, not just how much of it there is.

3a asks whether the passage answering a query answers it first. 3b asks
which questions a page draws impressions for and does not cover. Neither
can be judged from a title, an H1 and a word count, which is all the crawl
stored.
"""

from __future__ import annotations

from lxml import html as LH

from app.ingestion.crawler.parse import (
    extract_faq_questions,
    extract_json_ld,
    extract_sections,
)


def _doc(body: str):
    return LH.fromstring(f"<html><body>{body}</body></html>")


# ── Headings and the paragraph beneath ──


def test_a_heading_carries_the_paragraph_under_it():
    sections = extract_sections(
        _doc("<h2>What does it cost?</h2><p>Most inspections are $350.</p>")
    )
    assert [(s.level, s.heading, s.first_paragraph) for s in sections] == [
        (2, "What does it cost?", "Most inspections are $350.")
    ]


def test_the_paragraph_is_a_sibling_not_a_child():
    """On most pages the `<p>` follows the `<h2>`; it is not nested inside
    anything that contains both. Querying by nesting finds nothing."""
    sections = extract_sections(
        _doc("<div><h2>How long?</h2></div><div><p>About two hours.</p></div>")
    )
    assert sections[0].first_paragraph == "About two hours."


def test_only_the_first_paragraph_is_kept():
    sections = extract_sections(
        _doc("<h2>Cost</h2><p>First.</p><p>Second.</p>")
    )
    assert sections[0].first_paragraph == "First."


def test_a_heading_with_nothing_under_it_keeps_an_empty_paragraph():
    """Different from a heading we never saw: the answer-first test reads
    this as failing, which is the right answer for a bare heading."""
    sections = extract_sections(_doc("<h3>Our guarantee</h3>"))
    assert sections[0].heading == "Our guarantee"
    assert sections[0].first_paragraph == ""


def test_headings_come_back_in_document_order():
    sections = extract_sections(
        _doc("<h1>A</h1><p>1</p><h2>B</h2><p>2</p><h3>C</h3><p>3</p>")
    )
    assert [s.heading for s in sections] == ["A", "B", "C"]
    assert [s.level for s in sections] == [1, 2, 3]


def test_an_empty_heading_is_dropped():
    sections = extract_sections(_doc("<h2>  </h2><p>Orphaned.</p><h2>Real</h2><p>x</p>"))
    assert [s.heading for s in sections] == ["Real"]


def test_whitespace_in_markup_does_not_reach_the_text():
    sections = extract_sections(
        _doc("<h2>\n  What   does\n it cost?\n</h2><p>\n  $350.\n</p>")
    )
    assert sections[0].heading == "What does it cost?"
    assert sections[0].first_paragraph == "$350."


# ── Questions the page already answers ──


FAQ_SCHEMA = """
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
  {"@type":"Question","name":"Do you repair the slab too?",
   "acceptedAnswer":{"@type":"Answer","text":"Yes."}}]}
</script>
"""


def test_a_faqpage_question_is_found():
    doc = _doc(FAQ_SCHEMA)
    assert extract_faq_questions(doc, extract_json_ld(doc)) == [
        "Do you repair the slab too?"
    ]


def test_a_question_shaped_heading_counts_without_any_markup():
    """Plenty of real FAQs have no schema at all. A visitor still sees the
    question answered, and 3b must not offer to add it again."""
    doc = _doc("<h2>How long does it take?</h2><p>Two hours.</p>")
    assert extract_faq_questions(doc, []) == ["How long does it take?"]


def test_a_question_mark_is_enough_even_without_an_opener():
    doc = _doc("<h3>Slab leaks under a pool?</h3>")
    assert extract_faq_questions(doc, []) == ["Slab leaks under a pool?"]


def test_a_statement_heading_is_not_a_question():
    doc = _doc("<h2>Our guarantee</h2><h2>Pricing</h2>")
    assert extract_faq_questions(doc, []) == []


def test_schema_and_headings_are_merged_without_duplicates():
    doc = _doc(FAQ_SCHEMA + "<h2>Do you repair the slab too?</h2><h2>How long?</h2>")
    found = extract_faq_questions(doc, extract_json_ld(doc))
    assert found == ["Do you repair the slab too?", "How long?"]


def test_case_does_not_make_a_second_question():
    doc = _doc("<h2>How long does it take?</h2><h3>HOW LONG DOES IT TAKE?</h3>")
    assert len(extract_faq_questions(doc, [])) == 1


def test_an_h1_is_not_read_as_an_faq_entry():
    """A page titled with a question is answering it as the page, not
    listing it in an FAQ. Counting it would hide the real gap."""
    doc = _doc("<h1>What does slab leak detection cost?</h1><h2>Our process</h2>")
    assert extract_faq_questions(doc, []) == []
