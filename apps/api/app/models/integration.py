import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IntegrationProvider(str, enum.Enum):
    GA4 = "ga4"
    GSC = "gsc"
    SE_RANKING = "se_ranking"


class ConnectionStatus(str, enum.Enum):
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("client_id", "provider", name="uq_integrations_client_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(
            IntegrationProvider,
            name="integration_provider",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_property_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gsc_secondary_site_urls: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    connection_status: Mapped[ConnectionStatus] = mapped_column(
        Enum(
            ConnectionStatus,
            name="connection_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ConnectionStatus.NOT_CONNECTED,
    )
    last_sync_started: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fact_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
