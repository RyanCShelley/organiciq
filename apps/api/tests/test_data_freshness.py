from datetime import date

from app.models.client import Client
from app.models.config import OrganicChannel
from app.models.ga4 import FactGa4Traffic
from app.services import data_freshness


def test_a_source_with_no_data_is_overdue_and_one_with_recent_data_is_not(db, client_a: Client):
    db.add(FactGa4Traffic(client_id=client_a.id, date=date(2026, 10, 29), raw_url="https://x.example/", normalized_url="https://x.example/", channel=OrganicChannel.ORGANIC_SEARCH, sessions=5))
    db.commit()
    rows = {r["key"]: r for r in data_freshness.build(db, client_a, today=date(2026, 10, 30))}
    assert rows["ga4"]["through"] == "2026-10-29" and rows["ga4"]["overdue"] is False
    assert rows["bing"]["through"] is None and rows["bing"]["overdue"] is True


def test_the_same_source_goes_overdue_once_old_enough(db, client_a: Client):
    db.add(FactGa4Traffic(client_id=client_a.id, date=date(2026, 10, 20), raw_url="https://x.example/", normalized_url="https://x.example/", channel=OrganicChannel.ORGANIC_SEARCH, sessions=5))
    db.commit()
    rows = {r["key"]: r for r in data_freshness.build(db, client_a, today=date(2026, 10, 30))}
    assert rows["ga4"]["age_days"] == 10 and rows["ga4"]["overdue"] is True
