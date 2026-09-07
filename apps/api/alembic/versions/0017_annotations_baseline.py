"""Annotations + client baseline snapshot.

Revision ID: 0017_annotations_baseline
Revises: 0016_enterprise_tier
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_annotations_baseline"
down_revision: Union[str, None] = "0016_enterprise_tier"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

annotation_type = postgresql.ENUM(
    "growth_action",
    "content_published",
    "content_updated",
    "technical_change",
    "website_change",
    "conversion_change",
    "campaign_change",
    "algorithm_event",
    "manual_note",
    name="annotation_type",
    create_type=False,
)
annotation_result = postgresql.ENUM(
    "improved",
    "no_meaningful_change",
    "declined",
    "not_enough_data",
    "not_yet_measured",
    name="annotation_result",
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


def upgrade() -> None:
    bind = op.get_bind()
    annotation_type.create(bind, checkfirst=True)
    annotation_result.create(bind, checkfirst=True)

    op.add_column("clients", sa.Column("baseline_as_of", sa.Date(), nullable=True))
    op.add_column("clients", sa.Column("baseline_monthly_sessions", sa.Integer(), nullable=True))
    op.add_column("clients", sa.Column("baseline_monthly_leads", sa.Integer(), nullable=True))
    op.add_column(
        "clients",
        sa.Column("baseline_lead_rate_pct", sa.Numeric(8, 4), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("baseline_source", sa.String(length=32), nullable=True),
    )
    op.add_column("clients", sa.Column("baseline_notes", sa.Text(), nullable=True))

    op.create_table(
        "annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("annotation_type", annotation_type, nullable=False),
        sa.Column("growth_action", growth_action, nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topics.id"), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column(
            "baseline_metrics_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("success_metric", sa.String(length=255), nullable=True),
        sa.Column("teamwork_task_id", sa.String(length=128), nullable=True),
        sa.Column("completed_at", sa.Date(), nullable=True),
        sa.Column("measurement_start_date", sa.Date(), nullable=True),
        sa.Column("measurement_end_date", sa.Date(), nullable=True),
        sa.Column(
            "post_action_metrics_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "result",
            annotation_result,
            nullable=False,
            server_default="not_yet_measured",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "impact_summary_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_annotations_client_date", "annotations", ["client_id", "date"])
    op.create_index("ix_annotations_client_type", "annotations", ["client_id", "annotation_type"])


def downgrade() -> None:
    op.drop_index("ix_annotations_client_type", table_name="annotations")
    op.drop_index("ix_annotations_client_date", table_name="annotations")
    op.drop_table("annotations")
    op.drop_column("clients", "baseline_notes")
    op.drop_column("clients", "baseline_source")
    op.drop_column("clients", "baseline_lead_rate_pct")
    op.drop_column("clients", "baseline_monthly_leads")
    op.drop_column("clients", "baseline_monthly_sessions")
    op.drop_column("clients", "baseline_as_of")

    bind = op.get_bind()
    annotation_result.drop(bind, checkfirst=True)
    annotation_type.drop(bind, checkfirst=True)
