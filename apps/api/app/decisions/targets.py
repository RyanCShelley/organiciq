"""Decision 2 — score the candidates inside a branch.

    score = volume × intent × group × reach × fit

A product, so a zero on any factor removes the candidate rather than letting
four good factors carry a disqualifying one. A term with no search volume
cannot be worth an hour however well it fits, and a term already ranking
second has almost nothing left to win.

Each factor answers one question, and each is read from something stored
rather than inferred from a URL:

* **volume** — how many people search it. The size of the prize.
* **intent** — whether they are buying. Read from the declared target page's
  type, not from the words in the term.
* **group** — whether this is a term the client is judged on, from the
  priority flag on `keyword_targets`.
* **reach** — how far the term has to travel. Position four is a short trip;
  unranked against a difficult term is not.
* **fit** — whether the page that ranks is the page meant to rank. A term
  winning on the wrong URL is a different job from one winning on the right
  one, and the spec raises it as V-6 rather than optimising the wrong page.

Pure functions. The reasons are carried on the result so a card can say why
this target and not another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Candidate:
    """A keyword-page pair, before it is scored."""

    keyword: str
    #: The page declared to own this term, if anyone has said.
    target_url: str | None
    #: The URL actually ranking for it, from the rank tracker.
    ranking_url: str | None
    position: float | None
    volume: float | None
    difficulty: float | None = None
    priority: bool = False
    term_role: str | None = None
    #: commercial | conversion | article | utility | None, from the declared
    #: page's classification.
    target_page_type: str | None = None
    group_name: str | None = None


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    score: float
    factors: dict[str, float]
    #: Set when the term ranks on a URL that is not its declared target. The
    #: spec raises this as V-6 rather than optimising a page nobody chose.
    rehoming: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


#: Page types where somebody is buying rather than reading.
_COMMERCIAL_TYPES = frozenset({"commercial", "conversion"})


def intent_weight(target_page_type: str | None, *, informational: float = 0.4) -> float:
    """Commercial or transactional 1.0, informational 0.4.

    Read from the page the term is declared to own, not from the term's own
    words. "What is local seo" and "local seo services" differ by intent and
    not reliably by vocabulary, and a keyword matcher that guesses from
    wording put a glossary definition against a buying term.
    """
    if target_page_type is None:
        # Unknown is not informational. Without a declared page there is
        # nothing to read the intent from, and assuming the cheaper weight
        # quietly demotes every unmapped term.
        return 1.0
    return 1.0 if target_page_type in _COMMERCIAL_TYPES else informational


def group_weight(priority: bool, *, priority_weight: float = 1.5) -> float:
    """A priority-group term outranks an equally sized ordinary one."""
    return priority_weight if priority else 1.0


def reach(position: float | None, difficulty: float | None) -> float:
    """How much is left to win, by how far the term has to travel.

    Position one to three scores almost nothing — the clicks are already
    being earned, and the hour is better spent elsewhere. Unranked is the
    long trip, discounted by difficulty when it is known and by a flat
    pessimism when it is not, because an unknown difficulty is usually an
    unknown for a reason.
    """
    if position is None or position <= 0 or position > 100:
        if difficulty is None:
            return 0.15
        return 0.3 * max(0.0, 1.0 - difficulty / 100.0)
    if position <= 3:
        return 0.1
    if position <= 10:
        return 1.0
    if position <= 20:
        return 0.8
    if position <= 30:
        return 0.5
    return 0.15


def _same_page(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return left.rstrip("/").lower() == right.rstrip("/").lower()


def fit(candidate: Candidate) -> tuple[float, bool]:
    """Whether the page ranking is the page meant to rank.

    Returns the weight and whether this is a re-homing case. A term ranking
    on a URL nobody chose is not a weaker version of the same job — it is a
    decision about which page should own it, which is V-6.
    """
    if not candidate.target_url:
        # Nobody has said. Not penalised to zero: the term is still real, and
        # the engine's own answer is to ask for the mapping.
        return 0.7, False
    if candidate.ranking_url is None:
        # Declared, and not ranking anywhere. That is the ordinary case for a
        # term the client wants and does not have.
        return 1.0, False
    if _same_page(candidate.ranking_url, candidate.target_url):
        return 1.0, False
    return 0.5, True


def score_candidate(
    candidate: Candidate, *, thresholds: dict[str, Any] | None = None
) -> ScoredCandidate:
    thresholds = thresholds or {}
    volume = float(candidate.volume or 0.0)
    intent = intent_weight(
        candidate.target_page_type,
        informational=float(thresholds.get("intent_informational_weight", 0.4)),
    )
    group = group_weight(
        candidate.priority,
        priority_weight=float(thresholds.get("group_priority_weight", 1.5)),
    )
    travel = reach(candidate.position, candidate.difficulty)
    fit_weight, rehoming = fit(candidate)

    notes: list[str] = []
    if rehoming:
        notes.append(
            f"“{candidate.keyword}” ranks on {candidate.ranking_url}, not the "
            f"page it is mapped to"
        )
    if candidate.position is not None and 0 < candidate.position <= 3:
        notes.append("already in the top three, so there is little left to win")
    if candidate.target_url is None:
        notes.append("no page is declared to own this term")

    return ScoredCandidate(
        candidate=candidate,
        score=volume * intent * group * travel * fit_weight,
        factors={
            "volume": volume,
            "intent": intent,
            "group": group,
            "reach": travel,
            "fit": fit_weight,
        },
        rehoming=rehoming,
        notes=tuple(notes),
    )


def rank_candidates(
    candidates: list[Candidate], *, thresholds: dict[str, Any] | None = None
) -> list[ScoredCandidate]:
    """Best first, dropping anything a factor zeroed.

    A zero means one of the five questions answered "none" — no volume, or
    nothing left to win. Carrying it into the ranking at the bottom would put
    work that cannot pay on a screen that exists to decide what to spend an
    hour on.
    """
    scored = [score_candidate(c, thresholds=thresholds) for c in candidates]
    return sorted(
        (s for s in scored if s.score > 0),
        key=lambda s: (-s.score, s.candidate.keyword),
    )
