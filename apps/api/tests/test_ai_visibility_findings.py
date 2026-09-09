from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.job import DataWatermark, ValidationStatus
from app.models.gsc import FactGscPage
from app.models.seranking import FactSerAiCheck, FactSerAiPrompt, FactSerKeyword
from app.services.lever_engine import detect_keyword_rank_signal, diagnose
from tests.conftest import date_window


def test_detect_keyword_fell_top5_and_top10():
    assert (
        detect_keyword_rank_signal(current_position=8, previous_position=3)
        == "keyword_fell_top5"
    )
    assert (
        detect_keyword_rank_signal(current_position=14, previous_position=7)
        == "keyword_fell_top10"
    )
    assert (
        detect_keyword_rank_signal(current_position=None, previous_position=4)
        == "keyword_fell_top5"
    )
    assert detect_keyword_rank_signal(current_position=0, previous_position=None) == "keyword_not_ranking"
    assert detect_keyword_rank_signal(current_position=3, previous_position=5) is None


def test_diagnose_ai_visibility_keyword_and_prompt_rules(db, client_a):
    start, end = date_window(14)
    db.add(
        DataWatermark(
            id=uuid4(),
            client_id=client_a.id,
            source="gsc_pages",
            fact_through_date=end,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.add(
        DataWatermark(
            id=uuid4(),
            client_id=client_a.id,
            source="se_ranking_ai",
            fact_through_date=end,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("100"),
            clicks=Decimal("1"),
            ctr=Decimal("0.01"),
            average_position=Decimal("10"),
        )
    )
    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_a.id,
            site_engine_id="1",
            keyword_id="kw-1",
            keyword="managed seo services",
            volume=Decimal("400"),
            current_position=Decimal("12"),
            previous_position=Decimal("4"),
            ranking_url="https://example.com/services/seo",
            checked_at=end,
        )
    )
    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_a.id,
            site_engine_id="1",
            keyword_id="kw-2",
            keyword="brand keyword nowhere",
            volume=Decimal("200"),
            current_position=None,
            previous_position=None,
            checked_at=end,
        )
    )
    db.add(
        FactSerAiPrompt(
            id=uuid4(),
            client_id=client_a.id,
            llm_id="chatgpt",
            prompt_id="p1",
            engine="chatgpt",
            prompt="best seo agency for manufacturers",
            search_volume=Decimal("90"),
            brand_cited=False,
            brand_mentioned=False,
            url_position=None,
            checked_at=end,
        )
    )
    for day in (start, end):
        db.add(
            FactSerAiCheck(
                id=uuid4(),
                client_id=client_a.id,
                date=day,
                llm_id="chatgpt",
                prompt_id="p1",
                prompt="best seo agency for manufacturers",
                url_position=None,
                mention_position=None,
                brand_cited=False,
                brand_mentioned=False,
            )
        )
    db.commit()

    result = diagnose(db, client_a, from_date=start, to_date=end)
    ai = [row for row in result.findings if row.lever == "structured_data_ai"]
    signals = {row.evidence_json.get("audit_signal") for row in ai}
    assert "keyword_fell_top5" in signals
    assert "keyword_not_ranking" in signals
    assert "prompt_not_cited" in signals
    assert all(row.lever == "structured_data_ai" for row in ai)
    labels = {lever.label for lever in result.levers if lever.lever == "structured_data_ai"}
    assert labels == {"Search & AI Visibility"}
