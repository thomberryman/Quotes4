"""pdf ingestion workflow tables

Revision ID: 20260331_01_pdf
Revises: 20260330_01
Create Date: 2026-03-31 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
from app.models import PdfExtractionFieldResult, PdfExtractionLineItemResult, PdfExtractionRun

# revision identifiers, used by Alembic.
revision = "20260331_01_pdf"
down_revision = "20260330_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    PdfExtractionRun.__table__.create(bind=bind, checkfirst=True)
    PdfExtractionFieldResult.__table__.create(bind=bind, checkfirst=True)
    PdfExtractionLineItemResult.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    PdfExtractionLineItemResult.__table__.drop(bind=bind, checkfirst=True)
    PdfExtractionFieldResult.__table__.drop(bind=bind, checkfirst=True)
    PdfExtractionRun.__table__.drop(bind=bind, checkfirst=True)
