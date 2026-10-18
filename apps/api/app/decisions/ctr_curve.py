"""Expected organic CTR benchmarks from real SERP feature CTR data (percent)."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

REFERENCE_SCENARIO = "ai_overviews_desktop_aug_2026"

BENCHMARK_SOURCE = "organic_aggregated_2026_jul_us"
BENCHMARK_COLUMN = "Organic Aggregated"
UNDERPERFORMANCE_RATIO = 0.5
MIN_RECOVERABLE_CLICKS = 5

_DATA_PATH = Path(__file__).resolve().parent / "data" / "organic_ctr_benchmark_2026_jul_us.csv"

# Fallback if CSV is unavailable (Organic Aggregated column, positions 1–20).
_FALLBACK_ORGANIC_AGGREGATED_CTR: dict[int, float] = {
    1: 20.02,
    2: 10.36,
    3: 3.89,
    4: 1.71,
    5: 1.08,
    6: 0.73,
    7: 0.46,
    8: 0.47,
    9: 0.54,
    10: 0.58,
    11: 0.67,
    12: 0.7,
    13: 0.82,
    14: 0.88,
    15: 0.8,
    16: 0.67,
    17: 0.64,
    18: 0.55,
    19: 0.52,
    20: 0.27,
}


@lru_cache(maxsize=1)
def _load_organic_aggregated_curve() -> dict[int, float]:
    if not _DATA_PATH.is_file():
        return dict(_FALLBACK_ORGANIC_AGGREGATED_CTR)

    curve: dict[int, float] = {}
    with _DATA_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            position_raw = (row.get("position") or "").strip().strip('"')
            value_raw = (row.get(BENCHMARK_COLUMN) or "").strip().strip('"')
            if not position_raw or not value_raw:
                continue
            try:
                curve[int(position_raw)] = float(value_raw)
            except ValueError:
                continue

    return curve or dict(_FALLBACK_ORGANIC_AGGREGATED_CTR)


def expected_ctr_percent(position: float, *, scenario: str = "organic_aggregated") -> float:
    """Linearly interpolate Organic Aggregated CTR for fractional average positions."""
    if scenario not in ("organic_aggregated", "ai_overviews_desktop_aug_2026"):
        raise ValueError("Unknown CTR benchmark scenario")
    curve = ai_overview_curve() if scenario == "ai_overviews_desktop_aug_2026" else _load_organic_aggregated_curve()
    if position <= 1:
        return curve[1]
    if position >= 20:
        return curve[20]

    lower = int(position)
    upper = lower + 1
    if lower == upper or upper not in curve:
        rounded = int(round(position))
        rounded = max(1, min(20, rounded))
        return curve[rounded]

    lower_ctr = curve[lower]
    upper_ctr = curve[upper]
    weight = position - lower
    return lower_ctr + (upper_ctr - lower_ctr) * weight


#: The column to read when the SERP carries an AI Overview. Position one
#: falls from 20.02% to 12.82% and position two from 10.36% to 5.16%: the
#: answer is on the page already, so the ranking buys visibility and not a
#: visit. Ignoring this made every estimate on an AI-answered term too high.
AI_OVERVIEW_COLUMN = "AI Overviews + Organic"

#: What SE Ranking calls an AI Overview in `serp_features`.
AI_OVERVIEW_FEATURES = frozenset(
    {"ai_overview", "ai_overviews", "sge", "generative_ai", "ai_answer"}
)



@lru_cache(maxsize=1)
def ai_overview_curve() -> dict[int, float]:
    """User-supplied desktop scenario; header says August, not filename September.

    No enforced monotonicity: the observed second position exceeds the first.
    The decision diagnostic explicitly applies this user-selected curve across
    terms/devices/markets as a planning reference, without claiming AIO presence.
    """
    path = Path(__file__).resolve().parent / "data" / "ai_overviews_desktop_2026_aug.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return {int(row["Position"]): float(row["AI Overviews, Aug 2026"]) for row in rows}
