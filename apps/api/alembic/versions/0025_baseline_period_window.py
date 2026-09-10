"""Store the baseline snapshot's measured window as real columns.

Only `baseline_as_of` (the window's end) was persisted; the start survived as
free text inside `baseline_notes`, e.g. "GA4 2026-08-11→2026-09-09 (30d scaled
to 30d)". The dashboard needs both dates to say what the snapshot is frozen
between, and parsing a note string in the UI is not a foundation to build on.

Backfills from that note where it matches, and falls back to `baseline_as_of`
for the end date so manual snapshots still report something true.

Revision ID: 0025_baseline_period_window
Revises: 0024_purge_published_staging
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_baseline_period_window"
down_revision: Union[str, None] = "0024_purge_published_staging"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# "GA4 2026-08-11→2026-09-09 (...)" — capture both ISO dates.
_NOTE_WINDOW = r'(\d{4}-\d{2}-\d{2})\s*(?:→|->)\s*(\d{4}-\d{2}-\d{2})'


def upgrade() -> None:
    op.add_column("clients", sa.Column("baseline_period_start", sa.Date(), nullable=True))
    op.add_column("clients", sa.Column("baseline_period_end", sa.Date(), nullable=True))

    # Recover the window from the provenance note where one was written.
    op.execute(
        f"""
        UPDATE clients
        SET baseline_period_start = (substring(baseline_notes from '{_NOTE_WINDOW}'))::date,
            baseline_period_end   = (regexp_match(baseline_notes, '{_NOTE_WINDOW}'))[2]::date
        WHERE baseline_notes IS NOT NULL
          AND baseline_notes ~ '{_NOTE_WINDOW}'
        """
    )

    # Anything left (manual snapshots) at least knows when it was taken.
    op.execute(
        """
        UPDATE clients
        SET baseline_period_end = baseline_as_of
        WHERE baseline_period_end IS NULL
          AND baseline_as_of IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("clients", "baseline_period_end")
    op.drop_column("clients", "baseline_period_start")
