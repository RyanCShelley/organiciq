"""What model questions about one client have cost this month, across every feature that asks one, against the monthly cap."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ask_data import AskDataLog
from app.models.client import Client
from app.models.schema_tools import CtrTitleDraft, SchemaPageReport


def month_spend(db: Session, client: Client) -> Decimal:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = Decimal(0)
    for model in (AskDataLog, SchemaPageReport, CtrTitleDraft):
        total += db.query(func.coalesce(func.sum(model.cost_usd), 0)).filter(model.client_id == client.id, model.created_at >= start).scalar() or Decimal(0)
    return total
