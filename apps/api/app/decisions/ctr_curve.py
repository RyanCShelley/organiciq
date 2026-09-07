"""Expected organic CTR benchmarks from real SERP feature CTR data (percent)."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

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


def benchmark_source_label() -> str:
    return BENCHMARK_SOURCE


def expected_ctr_percent(position: float) -> float:
    """Linearly interpolate Organic Aggregated CTR for fractional average positions."""
    curve = _load_organic_aggregated_curve()
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


def ctr_performance_threshold(expected_ctr: float) -> float:
    """CTR (percent) below this vs benchmark is considered underperforming."""
    return expected_ctr * UNDERPERFORMANCE_RATIO


def recoverable_clicks_at_threshold(
    *,
    impressions: float,
    ctr_percent: float,
    expected_ctr: float,
) -> float:
    """Estimated clicks recoverable if CTR reached half the position benchmark."""
    target_ctr = ctr_performance_threshold(expected_ctr)
    if ctr_percent >= target_ctr:
        return 0.0
    return max(0.0, impressions * (target_ctr - ctr_percent) / 100.0)


def is_ctr_underperforming(
    *,
    ctr_percent: float,
    expected_ctr: float,
    impressions: float,
) -> bool:
    if ctr_percent >= ctr_performance_threshold(expected_ctr):
        return False
    return recoverable_clicks_at_threshold(
        impressions=impressions,
        ctr_percent=ctr_percent,
        expected_ctr=expected_ctr,
    ) >= MIN_RECOVERABLE_CLICKS
