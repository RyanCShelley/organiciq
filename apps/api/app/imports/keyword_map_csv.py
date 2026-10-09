"""Read an on-page keyword map export into keyword targets.

The map is a spreadsheet somebody maintains by hand: one row per page, a
main term, and a list of secondary terms with their volume and difficulty in
brackets. It is the answer to the question every ranking rule asks — which
page is this term for — and it has been sitting outside the system.

Parsing is deliberately strict about what counts as a term. The sheet uses
the keyword column for notes as well: `— (hub)`, `(brand + descriptor)`,
`— (proof page)`, `OrganicIQ (branded)`. None of those is a term anyone
searches, and importing them would put rows in the map that no rule can ever
match and nobody can tell apart from real ones.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

#: Section headers in the first column, e.g. "CORE PAGES". They carry no URL.
_SECTION = re.compile(r"^[A-Z][A-Z &]+$")

#: Trailing "(140/22)", "(1,000/62)", "(590/26, $45 CPC)" on a secondary term.
_METRICS = re.compile(r"\s*\((?:[\d,]+/[\d—-]+|no data|brand|reinforce|branded)[^)]*\)\s*$", re.I)

#: Placeholders the sheet puts in the keyword column when a page is not
#: targeting a term at all.
_NOT_A_TERM = re.compile(
    r"^\s*(—|-|)?\s*(\(.*\)|hub|utility|proof page)?\s*$|^\(.*\)$|\(branded\)|\(brand\)$",
    re.I,
)


@dataclass(frozen=True)
class MappedTerm:
    keyword: str
    target_url: str
    term_role: str
    section: str


def _clean_term(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = _METRICS.sub("", text).strip()
    # A bare note, or a note dressed as a term.
    if _NOT_A_TERM.match(text):
        return None
    if text.startswith("—") or text.lower() in {"hub", "utility"}:
        return None
    # "(brand + descriptor)" and friends.
    if text.startswith("(") and text.endswith(")"):
        return None
    return text.lower()


def parse_keyword_map(path: Path) -> list[MappedTerm]:
    terms: list[MappedTerm] = []
    seen: set[str] = set()
    section = ""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            url = (row.get("Page URL") or "").strip()
            if not url:
                continue
            if _SECTION.match(url):
                section = url.title()
                continue
            if not url.startswith("http"):
                continue

            main = _clean_term(row.get("Main Keyword", ""))
            if main and main not in seen:
                seen.add(main)
                terms.append(MappedTerm(main, url, "primary", section))

            for part in (row.get("Secondary Keywords (vol/KD)") or "").split("·"):
                term = _clean_term(part)
                if term and term not in seen:
                    seen.add(term)
                    terms.append(MappedTerm(term, url, "secondary", section))
    return terms
