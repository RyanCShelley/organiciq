from app.ingestion.seranking.tracker_stats import presence_from_statistics, weighted_presence


def test_presence_from_statistics_payload():
    payload = {
        "presence": {
            "mention_percent_in_top": 2.5,
            "link_percent_in_top": 5,
        },
        "stats": {"prompts_count": 40},
    }
    mention, link, prompts = presence_from_statistics(payload)
    assert mention == 2.5
    assert link == 5.0
    assert prompts == 40


def test_weighted_presence_across_engines():
    mention, link = weighted_presence(
        [
            (30, 2.0, 4.0),
            (10, 4.0, 8.0),
        ]
    )
    assert mention == 2.5
    assert link == 5.0
