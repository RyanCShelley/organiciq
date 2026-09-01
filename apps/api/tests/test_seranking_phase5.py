from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from app.core.settings import get_settings
from app.ingestion.seranking.pipeline_ai import run_seranking_ai_job
from app.ingestion.seranking.publish_ai import publish_seranking_ai
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerAiCheck, FactSerAiPrompt, StagingSerAiCheck, StagingSerAiPrompt


def _window(days: int = 14):
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start, end


def _connect_ser(db, client):
    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client.id,
            Integration.provider == IntegrationProvider.SE_RANKING,
        )
        .one()
    )
    integration.connection_status = ConnectionStatus.CONNECTED
    integration.external_property_id = "12345"
    integration.external_account_id = "SMA Marketing"
    db.commit()
    return integration


def test_ai_prompt_snapshot_from_checks(db, client_a):
    start, end = _window(3)
    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_ai",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    db.add(
        StagingSerAiPrompt(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            llm_id="12100",
            prompt_id="154612",
            prompt_llm_id="219919",
            engine="chatgpt",
            prompt="What services does SMA marketing offer",
            group_id="8005",
            group_name="Brand",
            search_volume=None,
            search_intent=["I"],
        )
    )
    db.add(
        StagingSerAiCheck(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            date=start,
            llm_id="12100",
            prompt_id="154612",
            prompt="What services does SMA marketing offer",
            url_position=Decimal("2"),
            mention_position=Decimal("3"),
        )
    )
    db.add(
        StagingSerAiCheck(
            job_id=job.id,
            client_id=client_a.id,
            raw={},
            date=end,
            llm_id="12100",
            prompt_id="154612",
            prompt="What services does SMA marketing offer",
            url_position=Decimal("1"),
            mention_position=Decimal("1"),
        )
    )
    db.commit()

    prompts_written, checks_written = publish_seranking_ai(db, job)
    assert prompts_written == 1
    assert checks_written == 2
    fact = db.query(FactSerAiPrompt).one()
    assert fact.brand_mentioned is True
    assert fact.brand_cited is True
    assert fact.url_position == Decimal("1")
    assert fact.mention_position == Decimal("1")
    assert fact.url_position_change == Decimal("1")
    assert fact.mention_position_change == Decimal("2")
    assert db.query(FactSerAiCheck).count() == 2


def test_seranking_ai_pipeline_with_mocked_api(db, client_a, monkeypatch):
    monkeypatch.setenv("SE_RANKING_API_KEY", "test-key")
    get_settings.cache_clear()
    _connect_ser(db, client_a)
    start, end = _window(3)

    job = SyncJob(
        id=uuid4(),
        client_id=client_a.id,
        source="se_ranking_ai",
        start_date=start,
        end_date=end,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()

    llm_engines = [{"id": 12100, "base_name": "chatgpt"}]
    prompt_groups = [{"id": "8005", "name": "Brand"}]
    prompts = [
        {
            "prompt_id": "154612",
            "prompt_llm_id": "219919",
            "prompt": "What services does SMA marketing offer",
            "group_id": "8005",
        }
    ]
    rankings = [
        {
            "prompt_id": "154612",
            "prompt": "What services does SMA marketing offer",
            "search_intent": ["I"],
            "positions": [
                {
                    "date": start.isoformat(),
                    "url_position": 2,
                    "mention_position": 3,
                    "urls_count": 12,
                    "mentions_count": 6,
                },
                {
                    "date": end.isoformat(),
                    "url_position": 1,
                    "mention_position": 1,
                    "urls_count": 6,
                    "mentions_count": 3,
                },
            ],
        }
    ]

    stats_payload = {
        "presence": {
            "mention_percent_in_top": 3,
            "link_percent_in_top": 5,
        },
        "stats": {"prompts_count": 1},
    }

    with (
        patch("app.ingestion.seranking.fetch_ai.ser_client.list_airt_llm_engines", return_value=llm_engines),
        patch("app.ingestion.seranking.fetch_ai.ser_client.list_airt_prompt_groups", return_value=prompt_groups),
        patch("app.ingestion.seranking.fetch_ai.ser_client.list_airt_prompts_paginated", return_value=prompts),
        patch("app.ingestion.seranking.fetch_ai.ser_client.list_airt_prompt_rankings_paginated", return_value=rankings),
        patch(
            "app.ingestion.seranking.fetch_ai.ser_client.get_airt_llm_statistics",
            return_value=stats_payload,
        ),
    ):
        result = run_seranking_ai_job(db, job)

    assert result.status in {SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL}
    assert result.validation_status == ValidationStatus.PASSED
    assert db.query(FactSerAiPrompt).filter(FactSerAiPrompt.client_id == client_a.id).count() == 1
    fact = db.query(FactSerAiPrompt).one()
    assert fact.prompt == "What services does SMA marketing offer"
    assert fact.group_name == "Brand"
    assert fact.brand_mentioned is True
    assert fact.brand_cited is True
    wm = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_a.id, DataWatermark.source == "se_ranking_ai")
        .one()
    )
    assert wm.fact_through_date is not None
    assert wm.validation_status == ValidationStatus.PASSED
    get_settings.cache_clear()
