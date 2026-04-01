"""add comparable recommendation persistence

Revision ID: 20260331_01_comparable
Revises: 20260330_01
Create Date: 2026-03-31 15:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models import (
    ComparableProjectLink,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
)

benchmark_actuals_status = sa.Enum(
    "none",
    "partial",
    "complete",
    name="benchmark_actuals_status",
    native_enum=False,
    length=32,
)

comparable_project_link_disposition = sa.Enum(
    "pinned",
    "excluded",
    name="comparable_project_link_disposition",
    native_enum=False,
    length=32,
)

# revision identifiers, used by Alembic.
revision = "20260331_01_comparable"
down_revision = "20260330_01"
branch_labels = None
depends_on = None


TABLES = [
    ComparableProjectLink.__table__,
    ProjectBenchmarkSummary.__table__,
    ProjectBenchmarkDisciplineSummary.__table__,
]


def upgrade() -> None:
    bind = op.get_bind()
    benchmark_actuals_status.create(bind, checkfirst=True)
    comparable_project_link_disposition.create(bind, checkfirst=True)
    for table in TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(TABLES):
        table.drop(bind=bind, checkfirst=True)
    comparable_project_link_disposition.drop(bind, checkfirst=True)
    benchmark_actuals_status.drop(bind, checkfirst=True)
