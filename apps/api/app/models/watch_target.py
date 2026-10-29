"""Strategic ownership is distinct from observed rankings and citations."""
import uuid
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class WatchTarget(Base):
    __tablename__ = "watch_targets"
    __table_args__ = (
        UniqueConstraint("client_id", "kind", "item_key", name="uq_watch_targets_item"),
        Index("ix_watch_targets_client", "client_id"),
        CheckConstraint("kind IN ('keyword', 'prompt')", name="ck_watch_targets_kind"),
        CheckConstraint("state IN ('existing', 'planned', 'unmapped', 'excluded')", name="ck_watch_targets_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    item_key: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="unmapped")
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    observation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
