"""mvp backend baseline

Revision ID: 20260330_01
Revises:
Create Date: 2026-03-30 23:59:00.000000
"""

from __future__ import annotations

from alembic import op
from app.models import Base

# revision identifiers, used by Alembic.
revision = "20260330_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_project_parties_primary_role
        ON project_parties (project_id, role)
        WHERE is_primary = true
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_company_contacts_primary_company
        ON company_contacts (company_id)
        WHERE is_primary = true
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_project_contacts_primary_contact
        ON project_contacts (project_id, contact_id)
        WHERE is_primary = true
        """
    )
    op.execute(
        """
        ALTER TABLE monthly_forecast_allocations
        ADD CONSTRAINT ck_monthly_forecast_allocations_month_first_day
        CHECK (EXTRACT(DAY FROM month) = 1)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_project_contacts_primary_contact")
    op.execute("DROP INDEX IF EXISTS ux_company_contacts_primary_company")
    op.execute("DROP INDEX IF EXISTS ux_project_parties_primary_role")
    op.execute(
        "ALTER TABLE monthly_forecast_allocations "
        "DROP CONSTRAINT IF EXISTS ck_monthly_forecast_allocations_month_first_day"
    )

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
