"""Which of the three is holding this client back this month.

The engine had ten actions and no judgement. Every rule fired on its own, the
results were ranked together by expected leads, and the output read as a menu —
twenty-five prompt gaps for a site whose actual problem was that it had just
relaunched and lost its rankings.

This picks one answer before anything is prescribed: **visibility, traffic or
conversion**. Visibility earns traffic, traffic earns leads, so the ladder runs
in that order and the first rung that is genuinely broken wins. If the market
cannot see the page, conversion work has limited leverage however good the
conversion finding looks.

Pure functions over plain signals. Nothing here touches the database, so each
rung can be tested at its own boundary without a fixture site.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Layer(str, Enum):
    """Matches `DiagnosticLayer` in the decision model, so a constraint and a
    finding can be compared without translating between two vocabularies."""

    VISIBILITY = "visibility"
    TRAFFIC = "traffic"
    CONVERSION = "conversion"


#: Upstream first. The order is the argument: visibility earns traffic earns
#: leads, so a broken rung makes everything below it a weaker bet.
LADDER: tuple[Layer, ...] = (Layer.VISIBILITY, Layer.TRAFFIC, Layer.CONVERSION)


@dataclass(frozen=True)
class LayerAssessment:
    """What one rung achieved against what it should have.

    `ratio` is the whole idea. Visibility is a share, traffic is clicks and
    conversion is leads — three quantities that cannot be compared until each
    is expressed as achieved over expected. Lower is worse.

    The ratio stays in its own natural units and carries its own `floor`,
    because the bars genuinely differ: a third of tracked terms in the top ten
    is respectable, earning only a third of the clicks your rankings should is
    not. Cross-layer comparison uses `headroom` — ratio over floor — so the
    question asked is "how close is each to its own bar", not "which number is
    smaller".

    `measurable` is not the same as a ratio of zero. A client with no Search
    Console has no traffic ratio; a client whose pages draw no clicks has one,
    and it is 0.0. Collapsing the two would make every unconfigured client look
    like a disaster.
    """

    layer: Layer
    measurable: bool
    ratio: float | None
    floor: float
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def below_floor(self) -> bool:
        return self.measurable and self.ratio is not None and self.ratio < self.floor

    @property
    def headroom(self) -> float | None:
        """Ratio against this layer's own bar. The only comparable number."""
        if not self.measurable or self.ratio is None or self.floor <= 0:
            return None
        return self.ratio / self.floor


@dataclass(frozen=True)
class Constraint:
    """The month's answer, and the evidence for it."""

    layer: Layer
    reason: str
    assessments: tuple[LayerAssessment, ...]
    #: True when nothing was below its floor and the worst ratio won instead.
    #: The sentence a reader needs is different: "this is broken" against
    #: "nothing is broken, this is the weakest".
    by_comparison: bool = False

    def of(self, layer: Layer) -> LayerAssessment | None:
        return next((a for a in self.assessments if a.layer is layer), None)


# ── Visibility ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VisibilitySignals:
    """Tracked keyword positions, and whether answer engines cite the brand."""

    #: `{top_3, top_10, top_20, beyond_20, not_ranking}` — buckets are
    #: exclusive, so top_10 means positions 4 to 10.
    keyword_distribution: dict[str, int] | None = None
    #: Share of tracked prompts whose answer links the domain, 0-100.
    ai_link_presence_pct: float | None = None
    tracked_prompts: int = 0


def assess_visibility(
    signals: VisibilitySignals,
    *,
    top10_floor: float,
    ai_citation_floor_pct: float,
) -> LayerAssessment:
    """Can the market see this client at all.

    Two independent readings — classic rankings and AI citations — and the
    worse one is taken. A site ranking well that no answer engine will quote
    has a visibility problem, and so does the reverse.
    """
    # (ratio, floor, reason, evidence) for each reading we can take.
    parts: list[tuple[float, float, str, dict[str, Any]]] = []

    dist = signals.keyword_distribution or {}
    tracked = sum(int(v or 0) for v in dist.values())
    if tracked > 0:
        in_top_10 = int(dist.get("top_3") or 0) + int(dist.get("top_10") or 0)
        share = in_top_10 / tracked
        parts.append(
            (
                share,
                top10_floor,
                f"{in_top_10} of {tracked} tracked terms are in the top ten",
                {"tracked_keywords": tracked, "in_top_10": in_top_10,
                 "top_10_share": round(share, 3)},
            )
        )

    if signals.ai_link_presence_pct is not None and signals.tracked_prompts > 0:
        pct = float(signals.ai_link_presence_pct)
        parts.append(
            (
                pct / 100.0,
                ai_citation_floor_pct / 100.0,
                f"answer engines cite the brand on {pct:.0f}% of tracked prompts",
                {"ai_link_presence_pct": round(pct, 1),
                 "tracked_prompts": signals.tracked_prompts},
            )
        )

    if not parts:
        return LayerAssessment(
            layer=Layer.VISIBILITY,
            measurable=False,
            ratio=None,
            floor=1.0,
            reason="no tracked keywords and no tracked prompts",
        )

    # The worse of the two readings, judged against each one's own bar. A site
    # ranking well that no answer engine will quote has a visibility problem,
    # and so does the reverse.
    ratio, floor, reason, _ev = min(
        parts, key=lambda p: (p[0] / p[1]) if p[1] > 0 else 1.0
    )
    merged: dict[str, Any] = {}
    for _r, _f, _s, ev in parts:
        merged.update(ev)
    return LayerAssessment(
        layer=Layer.VISIBILITY,
        measurable=True,
        ratio=ratio,
        floor=floor,
        reason=reason,
        evidence=merged,
    )


# ── Traffic ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrafficSignals:
    """Clicks earned against clicks the rankings should have earned.

    This is the honest normaliser for traffic: a site ranking tenth for
    everything and a site ranking third for everything should not be compared
    on raw clicks. Expected clicks come from the measured CTR curve at the
    positions actually held.
    """

    clicks: float | None = None
    expected_clicks: float | None = None
    impressions: float = 0.0


def assess_traffic(
    signals: TrafficSignals, *, min_impressions: float, floor: float
) -> LayerAssessment:
    if (
        signals.clicks is None
        or signals.expected_clicks is None
        or signals.impressions < min_impressions
    ):
        return LayerAssessment(
            layer=Layer.TRAFFIC,
            measurable=False,
            ratio=None,
            floor=1.0,
            reason="no Search Console data for this period",
        )
    if signals.expected_clicks <= 0:
        # Rankings so poor the curve predicts nothing. That is a visibility
        # problem being described in traffic's language, so traffic declines
        # to answer rather than reporting a divide-by-zero as perfection.
        return LayerAssessment(
            layer=Layer.TRAFFIC,
            measurable=False,
            ratio=None,
            floor=1.0,
            reason="rankings are too low for the CTR curve to expect any clicks",
        )

    ratio = signals.clicks / signals.expected_clicks
    return LayerAssessment(
        layer=Layer.TRAFFIC,
        measurable=True,
        ratio=ratio,
        floor=floor,
        reason=(
            f"{int(signals.clicks):,} clicks against "
            f"{int(signals.expected_clicks):,} the rankings should earn"
        ),
        evidence={
            "clicks": round(signals.clicks, 1),
            "expected_clicks": round(signals.expected_clicks, 1),
            "impressions": round(signals.impressions, 1),
        },
    )


# ── Conversion ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConversionSignals:
    """Leads against the goal in force for this window."""

    leads: float | None = None
    period_goal: float | None = None
    lead_events_configured: bool = False


def assess_conversion(signals: ConversionSignals, *, floor: float) -> LayerAssessment:
    if not signals.lead_events_configured:
        return LayerAssessment(
            layer=Layer.CONVERSION,
            measurable=False,
            ratio=None,
            floor=1.0,
            reason="no lead events configured, so there is nothing to measure against",
        )
    if signals.leads is None or not signals.period_goal:
        return LayerAssessment(
            layer=Layer.CONVERSION,
            measurable=False,
            ratio=None,
            floor=1.0,
            reason="no lead goal set for this period",
        )

    ratio = float(signals.leads) / float(signals.period_goal)
    return LayerAssessment(
        layer=Layer.CONVERSION,
        measurable=True,
        ratio=ratio,
        floor=floor,
        reason=(
            f"{int(signals.leads)} leads against a goal of {int(signals.period_goal)}"
        ),
        evidence={
            "leads": round(float(signals.leads), 1),
            "period_goal": round(float(signals.period_goal), 1),
        },
    )


# ── The ladder ──────────────────────────────────────────────────────────────


def select_constraint(assessments: list[LayerAssessment]) -> Constraint | None:
    """The one thing to work on, and why.

    Upstream wins. The first rung below its floor takes the month even when a
    lower rung is worse by ratio — a conversion fix on a page nobody can find
    is an hour spent on the wrong end of the funnel.

    With nothing broken, the weakest measurable rung wins and the reason says
    so differently: there is a difference between "this is broken" and
    "nothing is broken, this is the softest spot".
    """
    by_layer = {a.layer: a for a in assessments}
    measurable = [a for a in assessments if a.measurable and a.ratio is not None]
    if not measurable:
        return None

    for layer in LADDER:
        found = by_layer.get(layer)
        if found is not None and found.below_floor:
            return Constraint(
                layer=layer,
                reason=found.reason,
                assessments=tuple(assessments),
            )

    # Nothing broken, so the softest spot wins — compared on headroom, since
    # a raw ratio means something different on each rung.
    weakest = min(measurable, key=lambda a: (a.headroom or 1.0, LADDER.index(a.layer)))
    return Constraint(
        layer=weakest.layer,
        reason=weakest.reason,
        assessments=tuple(assessments),
        by_comparison=True,
    )
