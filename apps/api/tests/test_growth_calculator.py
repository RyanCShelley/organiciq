"""Growth calculator + baseline snapshot from GA4."""

from app.services.growth_calculator import plan_key_from_tier_name, project_leads


def test_launch_projection_matches_calculator_shape():
    result = project_leads(monthly_sessions=1000, monthly_leads=15, plan="launch")
    assert result["baseline_lead_rate_pct"] == 1.5
    assert result["checkpoints"][0]["monthly_leads"] == 15.0
    # 12mo: traffic * 0.872 * cvr * 1.596
    expected_12 = 1000 * (1 - 0.128) * (1.5 * 1.596 / 100)
    assert abs(result["checkpoints"][-1]["monthly_leads"] - expected_12) < 0.05
    assert result["suggested_monthly_lead_goal"] == round(expected_12)


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
