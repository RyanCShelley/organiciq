"""Every rule scores in the same unit: leads.

The engine briefly scored in two currencies. The original rules converted to
leads against a shared reference; four rules added later each invented a
divisor — impressions/2000, clicks/200, volume/1000 — chosen because the
output looked plausible. A cluster worth about one lead and a page losing
twelve both scored 100, so they sorted as equals.

Worse, it inverted the product's own order. Leads come first, then traffic,
then visibility — but the visibility rules reached 100 most cheaply, so the
scale argued against the priority it was meant to express.
"""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "app" / "services" / "lever_engine.py"

#: The one sanctioned way to turn a finding into a 0-100 impact. It takes
#: leads, applies the client's own reference, and discounts by how much the
#: estimate can be trusted.
NORMALISER = "normalize_business_impact"
#: Scorers that wrap the normaliser rather than bypassing it.
SCORERS = {
    NORMALISER,
    "score_technical_impact",
    "score_internal_linking_impact",
    "score_serp_ctr_impact",
    "score_ai_visibility_impact",
    "score_conversion_impact",
}


#: Search opportunities are a separate list that is never promoted to an
#: action, so they carry no impact and pass a literal zero.
UNSCORED_LEVERS = {"SEARCH_OPPORTUNITY_LEVER"}


def _is_unscored(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg == "lever" and isinstance(keyword.value, ast.Name):
            return keyword.value.id in UNSCORED_LEVERS
    return False


def _impact_arguments() -> list[tuple[int, ast.expr]]:
    """Every `impact=` passed to a scored finding constructor in the engine."""
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    found: list[tuple[int, ast.expr]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in {"_make_finding", "LeverFinding"}:
            continue
        if _is_unscored(node):
            continue
        for keyword in node.keywords:
            if keyword.arg == "impact":
                found.append((node.lineno, keyword.value))
    return found


def test_the_engine_has_findings_to_check():
    assert len(_impact_arguments()) >= 8


def test_no_rule_invents_its_own_impact_scale():
    """An inline arithmetic impact is a new currency, which is the bug."""
    offenders = []
    for lineno, value in _impact_arguments():
        if isinstance(value, ast.Name):
            # A variable, which the next test proves comes from a scorer.
            continue
        if isinstance(value, ast.Attribute):
            # assessment.impact — a scorer's own result.
            continue
        offenders.append(f"line {lineno}: {ast.unparse(value)}")

    assert offenders == [], (
        "impact must come from a scorer, not be computed inline: " + "; ".join(offenders)
    )


def test_every_impact_variable_is_assigned_from_a_scorer():
    """Catches `impact = clicks / 200 * 100` followed by `impact=impact`."""
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue

        names = set()
        for target in targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Tuple):
                names.update(el.id for el in target.elts if isinstance(el, ast.Name))
        if "impact" not in names:
            continue

        call = value
        name = getattr(getattr(call, "func", None), "id", None) or getattr(
            getattr(call, "func", None), "attr", None
        )
        if name not in SCORERS:
            offenders.append(f"line {node.lineno}: impact = {ast.unparse(value)}")

    assert offenders == [], (
        "impact must be assigned from a scorer so it stays denominated in "
        "leads: " + "; ".join(offenders)
    )


def test_the_guard_catches_a_reintroduced_divisor(tmp_path, monkeypatch):
    """Proof the guard works, rather than passing because it checks nothing."""
    import tests.test_impact_currency as module

    fake = tmp_path / "engine.py"
    fake.write_text(
        "def rule():\n"
        "    impact = clicks / 200.0 * 100.0\n"
        "    return _make_finding(lever=X, impact=impact)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ENGINE", fake)

    try:
        module.test_every_impact_variable_is_assigned_from_a_scorer()
    except AssertionError as exc:
        assert "clicks / 200.0" in str(exc)
    else:
        raise AssertionError("the guard did not catch an invented scale")


def test_keyword_impact_differentiates_by_search_volume():
    """It did not, and that was invisible until real output was read.

    Passing only recoverable_clicks sent this down the upstream fallback,
    where the click component caps at 15 and then takes a low-confidence
    haircut. Every term above roughly 400 searches a month scored an identical
    8.2, so twenty-five tracked keywords came back indistinguishable and all
    of them below the threshold to be worth doing.
    """
    from app.services.decision_impact import SiteBusinessContext, score_ai_visibility_impact

    site = SiteBusinessContext(
        site_lead_rate_pct=2.0,
        period_sessions=5000.0,
        period_leads=35,
        period_lead_goal=38,
        p90_page_sessions=400.0,
    )
    scores = [
        score_ai_visibility_impact(signal="keyword_not_ranking", volume=volume, site=site)[0]
        for volume in (150, 500, 1500, 5000)
    ]

    assert scores == sorted(scores), scores
    assert len(set(scores)) == len(scores), f"all terms scored the same: {scores}"
    # A big term has to be able to clear the actionable threshold at all.
    assert scores[-1] > 25
