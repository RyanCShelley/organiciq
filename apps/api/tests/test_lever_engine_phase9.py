from datetime import date
from uuid import uuid4

from app.decisions.ctr_curve import expected_ctr_percent
from app.models.job import DataWatermark, ValidationStatus


def _watermark(db, client_id, source: str, fact_through: date) -> None:
    db.add(
        DataWatermark(
            id=uuid4(),
            client_id=client_id,
            source=source,
            fact_through_date=fact_through,
            validation_status=ValidationStatus.PASSED,
        )
    )








def test_expected_ctr_curve():
    assert expected_ctr_percent(4) == 1.71
    assert expected_ctr_percent(5) == 1.08
    assert expected_ctr_percent(10) == 0.58
























# --- T6 ---------------------------------------------------------------------




