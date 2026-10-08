"""Every tuning knob has to turn something.

`decision_thresholds` is merged over these defaults, and the overrides are
settable per client. A key nothing reads is worse than a missing one: it
offers a dial, accepts a value for it, reports it back, and changes
nothing. Seventeen of them were left behind by rules that had been
deleted, two of which were `rule_*_enabled` flags for rules that no longer
exist — so switching them off did nothing, and switching them on did
nothing either.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = ROOT / "app" / "decisions" / "thresholds.py"
WEB = ROOT.parent / "web"

def _default_keys() -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(ast.parse(THRESHOLDS.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    return keys


def _corpus() -> str:
    parts = []
    for base in (ROOT / "app", ROOT / "tests"):
        for path in base.rglob("*.py"):
            if path == THRESHOLDS:
                continue
            parts.append(path.read_text(encoding="utf-8"))
    if WEB.is_dir():
        for path in WEB.rglob("*.ts"):
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            parts.append(path.read_text(encoding="utf-8"))
        for path in WEB.rglob("*.tsx"):
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_every_default_threshold_is_read_by_something():
    corpus = _corpus()
    orphans = sorted(key for key in _default_keys() if key not in corpus)
    assert orphans == [], (
        "these thresholds are offered as tuning knobs and turn nothing: "
        + ", ".join(orphans)
    )


def test_no_threshold_is_composed_at_runtime():
    """Every key is a literal, so the scan above sees all of them.

    There used to be two families built from a rule id — `reliability_{rule}`
    and `flat_credit_{_credit_key(rule)}` — which the scan had to be told to
    skip, and an exemption that wide hides real orphans behind it. Both
    families went with the lead valuation: the reliability priors were all
    1.0, a multiplier that did nothing, and the flat credits were the made-up
    numbers that put twenty-five identically priced prompts on the screen.
    """
    # Built rather than written, because this file is in the corpus and a
    # literal needle here would match itself.
    needles = ['f"' + stem for stem in ("reliability_", "flat_credit_")]
    corpus = _corpus()
    for needle in needles:
        assert needle not in corpus, (
            f"{needle} composes a threshold key at runtime, so the orphan "
            "scan cannot see it. Spell the key out, or re-introduce an "
            "exemption here deliberately."
        )
