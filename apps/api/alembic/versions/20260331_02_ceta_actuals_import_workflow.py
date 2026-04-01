"""add ceta actuals import workflow tables

Revision ID: 20260331_02_ceta
Revises: 20260331_01_comparable, 20260331_01_pdf
Create Date: 2026-03-31 17:10:00.000000
"""

from __future__ import annotations

from alembic import op
from app.models import (
    ActualMappingDecision,
    ActualMappingRule,
    CetaImport,
    CetaImportRow,
    CetaImportRowCandidate,
    CetaImportRowIssue,
    MappedActual,
    ProjectExternalReference,
    ReferenceTermAlias,
)

# revision identifiers, used by Alembic.
revision = "20260331_02_ceta"
down_revision = ("20260331_01_comparable", "20260331_01_pdf")
branch_labels = None
depends_on = None


TABLES = [
    CetaImport.__table__,
    CetaImportRow.__table__,
    CetaImportRowIssue.__table__,
    CetaImportRowCandidate.__table__,
    ProjectExternalReference.__table__,
    ReferenceTermAlias.__table__,
    ActualMappingRule.__table__,
    ActualMappingDecision.__table__,
    MappedActual.__table__,
]


def upgrade() -> None:
    bind = op.get_bind()
    CetaImport.metadata.create_all(bind=bind, tables=TABLES, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    CetaImport.metadata.drop_all(bind=bind, tables=TABLES, checkfirst=True)
