"""Growth calculator + baseline snapshot from GA4."""

from app.services.growth_calculator import plan_key_from_tier_name, project_leads


def test_launch_projection_matches_calculator_shape():
    result = project_leads(monthly_sessions=1000, monthly_leads=15, plan="launch", monthly_gsc_clicks=400, ai_visibility_pct=20)
    assert result["baseline_lead_rate_pct"] == 1.5
    assert result["checkpoints"][0]["monthly_leads"] == 15.0
    assert result["checkpoints"][0]["monthly_gsc_clicks"] == 400.0
    assert result["checkpoints"][0]["ai_visibility_pct"] == 20.0
    # 12mo Launch: +5% traffic, +8% GSC clicks, +5pts AI visibility, diminishing-returns CVR at 1.5%
    eff_mult = 1 + (1.596 - 1) / (1 + 1.5 / 2.0)
    expected_12 = 1000 * 1.05 * (1.5 * eff_mult / 100)
    assert abs(result["checkpoints"][-1]["monthly_leads"] - expected_12) < 0.05
    assert result["suggested_monthly_lead_goal"] == round(expected_12)
    assert result["suggested_monthly_traffic_goal"] == 1050
    assert result["suggested_monthly_visibility_clicks_goal"] == 432
    assert result["suggested_ai_visibility_pct_goal"] == 25.0


def test_high_starting_cvr_tapers_with_diminishing_returns():
    # Robinson-like high baseline CVR (5.92%) grows via +20% J-curve traffic and tapered CVR (~7.79%), not 13%+
    high = project_leads(monthly_sessions=3396, monthly_leads=201, plan="lead", monthly_gsc_clicks=461)
    cvr_12 = high["checkpoints"][-1]["lead_rate_pct"]
    assert 7.0 < cvr_12 < 8.5
    assert high["checkpoints"][-1]["monthly_sessions"] == round(3396 * 1.20, 2)
    assert high["suggested_monthly_traffic_goal"] == round(3396 * 1.20)
    assert high["suggested_monthly_visibility_clicks_goal"] == round(461 * 1.30)
    assert 300 <= high["suggested_monthly_lead_goal"] <= 330


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
