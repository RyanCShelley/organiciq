from app.decisions.ctr_curve import expected_ctr_percent


def test_expected_ctr_uses_organic_aggregated_benchmark():
    assert expected_ctr_percent(4) == 1.71
    assert expected_ctr_percent(5) == 1.08
    assert expected_ctr_percent(10) == 0.58


def test_expected_ctr_interpolates_fractional_positions():
    at_4_8 = expected_ctr_percent(4.8)
    assert 1.08 < at_4_8 < 1.71
    assert round(at_4_8, 2) == 1.21




