"""Decision Engine records and configurable thresholds.

Revision ID: 0011_decisions
Revises: 0010_facts_gsc_daily
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_decisions"
down_revision: Union[str, None] = "0010_facts_gsc_daily"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

decision_type = postgresql.ENUM(
    "bottleneck",
    "opportunity",
    "evidence",
    "content_planning_signal",
    name="decision_type",
    create_type=False,
)
growth_action = postgresql.ENUM(
    "internal_linking",
    "technical_seo",
    "serp_ctr",
    "structured_data_ai",
    "conversion_path",
    name="growth_action",
    create_type=False,
)
decision_priority = postgresql.ENUM("high", "medium", "low", name="decision_priority", create_type=False)
decision_status = postgresql.ENUM(
    "new",
    "reviewed",
    "accepted",
    "dismissed",
    "task_created",
    "completed",
    "measuring",
    "validated",
    name="decision_status",
    create_type=False,
)
diagnostic_layer = postgresql.ENUM(
    "visibility",
    "traffic",
    "conversion",
    name="diagnostic_layer",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    decision_type.create(bind, checkfirst=True)
    growth_action.create(bind, checkfirst=True)
    decision_priority.create(bind, checkfirst=True)
    decision_status.create(bind, checkfirst=True)
    diagnostic_layer.create(bind, checkfirst=True)

    op.create_table(
        "decision_thresholds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", name="uq_decision_thresholds_client"),
    )

    op.create_table(
        "decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("rule_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("decision_type", decision_type, nullable=False),
        sa.Column("growth_action", growth_action, nullable=True),
        sa.Column("diagnostic_layer", diagnostic_layer, nullable=False),
        sa.Column("priority", decision_priority, nullable=False, server_default="medium"),
        sa.Column("status", decision_status, nullable=False, server_default="new"),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topics.id"), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("keyword", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("baseline_metrics_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("success_metric", sa.String(255), nullable=False),
        sa.Column("date_range_start", sa.Date(), nullable=False),
        sa.Column("date_range_end", sa.Date(), nullable=False),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "client_id",
            "rule_key",
            "date_range_start",
            "date_range_end",
            name="uq_decisions_rule_window",
        ),
    )


def downgrade() -> None:
    op.drop_table("decisions")
    op.drop_table("decision_thresholds")
    bind = op.get_bind()
    diagnostic_layer.drop(bind, checkfirst=True)
    decision_status.drop(bind, checkfirst=True)
    decision_priority.drop(bind, checkfirst=True)
    growth_action.drop(bind, checkfirst=True)
    decision_type.drop(bind, checkfirst=True)
