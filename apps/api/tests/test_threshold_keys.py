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

#: Keys built at runtime from a rule id, so the literal never appears.
#: `value.py` reads `f"reliability_{rule_id}"` and
#: `f"flat_credit_{_credit_key(rule_id)}"`.
DYNAMIC_PREFIXES = ("reliability_", "flat_credit_")


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
    orphans = sorted(
        key
        for key in _default_keys()
        if not key.startswith(DYNAMIC_PREFIXES) and key not in corpus
    )
    assert orphans == [], (
        "these thresholds are offered as tuning knobs and turn nothing: "
        + ", ".join(orphans)
    )


def test_the_dynamic_families_are_still_built_the_way_this_test_assumes():
    """The exemption above is only safe while the code really does compose
    these names. If that changes, the exemption hides real orphans."""
    value = (ROOT / "app" / "decisions" / "actions" / "value.py").read_text(encoding="utf-8")
    assert 'f"reliability_{rule_id}"' in value
    assert 'f"flat_credit_{_credit_key(rule_id)}"' in value


def test_every_dynamic_key_belongs_to_a_rule_the_engine_still_has():
    """A `reliability_7` left behind by a deleted rule is as dead as any
    other orphan; it is just spelled in a way the scan cannot see."""
    from app.decisions.actions.value import DEFAULT_MINUTES, _CREDIT_KEYS
    from app.services.lever_engine import ACTION_RULE_IDS

    live = set(ACTION_RULE_IDS.values()) | set(DEFAULT_MINUTES)
    suffixes = {f"reliability_{rule}" for rule in live}
    suffixes |= {f"flat_credit_{_CREDIT_KEYS.get(rule, rule)}" for rule in live}
    suffixes.add("reliability_default")

    orphans = sorted(
        key
        for key in _default_keys()
        if key.startswith(DYNAMIC_PREFIXES) and key not in suffixes
    )
    assert orphans == [], "tuned for rules the engine no longer has: " + ", ".join(orphans)
