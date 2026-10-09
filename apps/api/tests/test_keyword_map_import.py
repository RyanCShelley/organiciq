"""Reading the on-page keyword map.

The sheet uses the keyword column for notes as well as terms — `— (hub)`,
`(brand + descriptor)`, `— (proof page)`, `OrganicIQ (branded)`. Importing
those would fill the map with rows no rule can match and nobody can tell
apart from real ones.
"""

from __future__ import annotations

from pathlib import Path

from app.imports.keyword_map_csv import parse_keyword_map

HEADER = (
    "Page URL,Main Keyword,Vol,KD,Secondary Keywords (vol/KD),"
    "Suggested Title Tag,Chars,Suggested Meta Description,Chars\n"
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "map.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def test_a_main_term_is_primary_and_secondaries_are_secondary(tmp_path):
    rows = parse_keyword_map(
        _write(
            tmp_path,
            'https://x.com/seo,seo agency,27100,68,"seo company (18,100/68) · '
            'b2b seo agency (240/9)",T,1,D,1\n',
        )
    )
    assert [(r.keyword, r.term_role) for r in rows] == [
        ("seo agency", "primary"),
        ("seo company", "secondary"),
        ("b2b seo agency", "secondary"),
    ]
    assert all(r.target_url == "https://x.com/seo" for r in rows)


def test_volume_and_difficulty_are_stripped(tmp_path):
    rows = parse_keyword_map(
        tmp_path
        and _write(
            tmp_path,
            'https://x.com/ppc,ppc services,590,28,"ppc management company '
            '(590/26, $45 CPC) · paid search agency (260/13)",T,1,D,1\n',
        )
    )
    assert "ppc management company" in {r.keyword for r in rows}
    assert not any("/" in r.keyword or "$" in r.keyword for r in rows)


def test_the_notes_in_the_keyword_column_are_not_terms(tmp_path):
    """Every one of these is really in SMA's sheet."""
    rows = parse_keyword_map(
        _write(
            tmp_path,
            "https://x.com/blog/,— (hub),,,,T,1,D,1\n"
            "https://x.com/results,(brand + descriptor),—,—,—,T,1,D,1\n"
            "https://x.com/case,— (proof page),,,,T,1,D,1\n"
            "https://x.com/opt-out/,— (utility),,,,T,1,D,1\n",
        )
    )
    assert rows == []


def test_section_headers_are_not_pages(tmp_path):
    rows = parse_keyword_map(
        _write(
            tmp_path,
            "CORE PAGES,,,,,,,,\n"
            "https://x.com/,organic growth agency,10,30,,T,1,D,1\n"
            "GLOSSARY,,,,,,,,\n"
            "https://x.com/g/what-is-seo,what is seo,27100,99,,T,1,D,1\n",
        )
    )
    assert [r.section for r in rows] == ["Core Pages", "Glossary"]


def test_a_term_is_claimed_by_the_first_page_that_lists_it(tmp_path):
    """A term on two pages is the re-homing question the engine raises as
    V-6. The import must not silently give it two owners."""
    rows = parse_keyword_map(
        _write(
            tmp_path,
            "https://x.com/a,shared term,10,1,,T,1,D,1\n"
            "https://x.com/b,shared term,10,1,,T,1,D,1\n",
        )
    )
    assert len(rows) == 1
    assert rows[0].target_url == "https://x.com/a"


def test_terms_are_lowercased(tmp_path):
    """Search Console reports queries lowercased, and the engine looks the
    mapping up by the lowercased term."""
    rows = parse_keyword_map(
        _write(tmp_path, "https://x.com/,Local SEO Agency,10,1,,T,1,D,1\n")
    )
    assert rows[0].keyword == "local seo agency"
