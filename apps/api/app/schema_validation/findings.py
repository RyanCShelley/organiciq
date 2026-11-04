"""What the schema validator reports, and how it is classified.

Two things are kept apart on every finding:

* the **layer**: `schemaorg` (is the markup valid Schema.org?), `graph` (do the entities in the JSON-LD hold together?), `google` (does it make the page
  eligible for a Google search feature?) or `recommendation` (a contextual suggestion no standard requires);
* the **category**: `error` (technically wrong), `warning` (valid-looking markup that conflicts with the vocabulary, a feature's required fields or its own
  graph), `enhancement` (worth adding, nothing is wrong) and `informational` (valid, but worth knowing).

A property Google does not use is never an error, and a missing recommendation is never a warning: the category follows from the layer's own rules, written
down beside each rule. Findings carry the evidence from the markup, so each one can be checked against the page.
"""

from __future__ import annotations

import builtins
from dataclasses import asdict, dataclass, field
from typing import Any

ERROR, WARNING, ENHANCEMENT, INFORMATIONAL = "error", "warning", "enhancement", "informational"
CATEGORIES = (ERROR, WARNING, ENHANCEMENT, INFORMATIONAL)
RANK = {c: i for i, c in enumerate(CATEGORIES)}
LAYERS = ("schemaorg", "graph", "google", "recommendation")

SCHEMA_DOCS = "https://schema.org/docs/full.html"
GOOGLE_INTRO = "https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data"
GOOGLE_GALLERY = "https://developers.google.com/search/docs/appearance/structured-data/search-gallery"


def schema_doc(term: str) -> str:
    return f"https://schema.org/{term}"


@dataclass
class Finding:
    rule_id: str
    layer: str
    category: str
    title: str  # what this is, without the page's own values: the template-level text
    message: str  # the same with this page's values: what a person reads
    explanation: str
    recommendation: str
    doc: str
    url: str = ""
    entity_id: str | None = None
    type: str | None = None
    property: str | None = None
    evidence: Any = None
    auto_fixable: bool = False
    confidence: str = "high"  # high, medium, low
    fields: dict[str, Any] = field(default_factory=dict)

    @builtins.property
    def template_key(self) -> str:
        """What groups findings across pages: the rule and the type and property it concerns, not the page, the entity's @id or the values."""
        return "|".join((self.rule_id, self.type or "", self.property or ""))

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["template_key"] = self.template_key
        return d


def summarize(findings: list[Finding]) -> dict[str, int]:
    out = {c: 0 for c in CATEGORIES}
    for f in findings:
        out[f.category] += 1
    return out
