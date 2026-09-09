from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SchedulerCheckpoint(Base):
    __tablename__ = "scheduler_checkpoints"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_run_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
