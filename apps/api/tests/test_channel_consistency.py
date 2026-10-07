"""Anything that becomes a growth action is measured on one set of channels.

This engine has written the same bug three times: a page selected because
its organic visitors convert nothing, then valued against leads from every
channel, so the page looks like it converts and the action is thrown away.
ACC Tek's homepage was the third — 103 organic sessions, no organic leads,
five leads from referral, action scored at zero and discarded.

Each fix was correct and local, and the next one happened anyway, because
nothing stated the rule. This does. It reads the engine rather than running
it, so it cannot be satisfied by a passing run on data that happens not to
expose the mismatch — which is exactly how it survived three times.
"""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "app" / "services" / "lever_engine.py"

#: The two reads that decide what a growth action is worth. Both take a
#: `channels` argument, and both must be given the managed set.
SCOPED_READS = {"load_page_business_contexts", "_t1_inputs"}

#: The rules that may read every channel. A form that stopped firing stopped
#: for everyone, so every visitor is the evidence — and these report rather
#: than spending a client's monthly allowance.
TRACKING_READS = {"_sessions_by_page", "_leads_by_page"}


def _tree() -> ast.Module:
    return ast.parse(ENGINE.read_text(encoding="utf-8"))


def _calls(name: str) -> list[ast.Call]:
    found = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if called == name:
                found.append(node)
    return found


def _keyword(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == name:
            return ast.unparse(kw.value)
    return None


def test_the_valuation_reads_only_managed_channels():
    """`load_page_business_contexts` sets the site and page-type lead rates,
    every conversion shortfall, and whether a page looks like it converts."""
    calls = _calls("load_page_business_contexts")
    assert calls, "the engine must still build page contexts"
    for call in calls:
        assert _keyword(call, "channels") == "MANAGED_CHANNELS", (
            f"line {call.lineno}: page contexts must be scoped to MANAGED_CHANNELS"
        )


def test_the_trigger_that_picks_a_page_is_scoped_the_same_way():
    """`_t1_inputs` chooses which pages are leaking. It reads organic
    sessions and organic leads; the valuation has to agree."""
    source = ENGINE.read_text(encoding="utf-8")
    start = source.index("def _t1_inputs(")
    end = source.index("\ndef ", start + 1)
    body = source[start:end]
    assert body.count("MANAGED_CHANNELS") >= 2, (
        "T1 must scope both its sessions and its leads to the managed channels"
    )


def test_both_halves_of_a_rate_take_the_same_channel_argument():
    """A rate is sessions over leads. The two helpers that supply them must
    offer the same scoping, or one of them silently answers a different
    question from the other."""
    tree = _tree()
    signatures = {
        node.name: {a.arg for a in node.args.kwonlyargs}
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in TRACKING_READS
    }
    assert set(signatures) == TRACKING_READS, f"missing: {TRACKING_READS - set(signatures)}"
    for name, kwonly in signatures.items():
        assert "channels" in kwonly, f"{name} cannot be scoped, so it cannot be paired safely"


def test_a_rule_pairs_sessions_and_leads_on_the_same_channels():
    """Catches the actual mistake: one of the pair scoped and the other not,
    inside the same function."""
    offenders = []
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.FunctionDef):
            continue
        scopes = {}
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            called = getattr(call.func, "id", None)
            if called in TRACKING_READS:
                scopes.setdefault(called, set()).add(_keyword(call, "channels"))
        if len(scopes) == 2:
            seen = set().union(*scopes.values())
            if len(seen) > 1:
                offenders.append(f"{node.name} (line {node.lineno}): {scopes}")
    assert offenders == [], (
        "sessions and leads scoped differently in one rule: " + "; ".join(offenders)
    )
