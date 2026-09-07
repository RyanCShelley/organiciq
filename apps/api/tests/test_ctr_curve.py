from app.decisions.ctr_curve import (
    expected_ctr_percent,
    is_ctr_underperforming,
    recoverable_clicks_at_threshold,
)


def test_expected_ctr_uses_organic_aggregated_benchmark():
    assert expected_ctr_percent(4) == 1.71
    assert expected_ctr_percent(5) == 1.08
    assert expected_ctr_percent(10) == 0.58


def test_expected_ctr_interpolates_fractional_positions():
    at_4_8 = expected_ctr_percent(4.8)
    assert 1.08 < at_4_8 < 1.71
    assert round(at_4_8, 2) == 1.21


def test_moderate_ctr_no_longer_over_flagged_at_position_5():
    expected = expected_ctr_percent(5.0)
    assert expected == 1.08
    assert is_ctr_underperforming(ctr_percent=1.0, expected_ctr=expected, impressions=5000) is False


def test_severe_ctr_still_flags_with_recoverable_clicks():
    expected = expected_ctr_percent(5.0)
    assert is_ctr_underperforming(ctr_percent=0.06, expected_ctr=expected, impressions=4580) is True
    recoverable = recoverable_clicks_at_threshold(
        impressions=4580,
        ctr_percent=0.06,
        expected_ctr=expected,
    )
    assert recoverable >= 5
