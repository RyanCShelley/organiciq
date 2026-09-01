"""Expected organic CTR by average position (2026 blended curve, percent)."""

from __future__ import annotations

# Positions 1–20; tail positions use the position-20 rate.
EXPECTED_CTR_PERCENT_BY_POSITION: dict[int, float] = {
    1: 28.0,
    2: 15.5,
    3: 11.0,
    4: 8.2,
    5: 6.1,
    6: 4.8,
    7: 3.9,
    8: 3.2,
    9: 2.7,
    10: 2.3,
    11: 2.0,
    12: 1.8,
    13: 1.6,
    14: 1.4,
    15: 1.2,
    16: 1.1,
    17: 1.0,
    18: 0.9,
    19: 0.85,
    20: 0.8,
}


def expected_ctr_percent(position: float) -> float:
    if position <= 0:
        return EXPECTED_CTR_PERCENT_BY_POSITION[1]
    rounded = int(round(position))
    if rounded <= 1:
        return EXPECTED_CTR_PERCENT_BY_POSITION[1]
    if rounded >= 20:
        return EXPECTED_CTR_PERCENT_BY_POSITION[20]
    return EXPECTED_CTR_PERCENT_BY_POSITION[rounded]
