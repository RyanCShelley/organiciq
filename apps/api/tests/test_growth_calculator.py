"""Growth calculator + baseline snapshot from GA4."""

from app.services.growth_calculator import plan_key_from_tier_name, project_leads


def test_launch_projection_matches_calculator_shape():
    result = project_leads(monthly_sessions=1000, monthly_leads=15, plan="launch")
    assert result["baseline_lead_rate_pct"] == 1.5
    assert result["checkpoints"][0]["monthly_leads"] == 15.0
    # 12mo with diminishing returns at 1.5% CVR: 1 + (1.596 - 1) / (1 + 1.5/2.0)
    eff_mult = 1 + (1.596 - 1) / (1 + 1.5 / 2.0)
    expected_12 = 1000 * (1 - 0.128) * (1.5 * eff_mult / 100)
    assert abs(result["checkpoints"][-1]["monthly_leads"] - expected_12) < 0.05
    assert result["suggested_monthly_lead_goal"] == round(expected_12)


def test_high_starting_cvr_tapers_with_diminishing_returns():
    # Robinson-like high baseline CVR (5.92%) should not balloon to 13%+
    high = project_leads(monthly_sessions=3396, monthly_leads=201, plan="lead")
    cvr_12 = high["checkpoints"][-1]["lead_rate_pct"]
    assert 7.0 < cvr_12 < 8.5
    assert high["checkpoints"][-1]["monthly_sessions"] == 3396.0
    assert 250 <= high["suggested_monthly_lead_goal"] <= 280


def test_lift_lead_scale_above_launch():
    launch = project_leads(monthly_sessions=1000, monthly_leads=15, plan="launch")
    lift = project_leads(monthly_sessions=1000, monthly_leads=15, plan="lift")
    lead = project_leads(monthly_sessions=1000, monthly_leads=15, plan="lead")
    assert lift["suggested_monthly_lead_goal"] > launch["suggested_monthly_lead_goal"]
    assert lead["suggested_monthly_lead_goal"] > lift["suggested_monthly_lead_goal"]


def test_tier_name_mapping():
    assert plan_key_from_tier_name("Launch") == "launch"
    assert plan_key_from_tier_name("Legacy") == "launch"
    assert plan_key_from_tier_name("Lift") == "lift"
    assert plan_key_from_tier_name("Lead") == "lead"
    assert plan_key_from_tier_name("Enterprise") == "lead"
