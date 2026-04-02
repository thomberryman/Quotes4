"""normalize forecast phasing schema and allocation semantics

Revision ID: 20260401_04_phase_cleanup
Revises: 20260401_03_phase_draft
Create Date: 2026-04-01 23:45:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260401_04_phase_cleanup"
down_revision = "20260401_03_phase_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    allocation_columns = {
        column["name"] for column in inspector.get_columns("monthly_forecast_allocations")
    }
    if "manual_note" not in allocation_columns:
        op.add_column(
            "monthly_forecast_allocations",
            sa.Column("manual_note", sa.Text(), nullable=True),
        )

    bind.execute(
        sa.text(
            """
            UPDATE projects
            SET revenue_allocation_method = :system_method,
                cadence_profile_type = COALESCE(cadence_profile_type, :default_profile)
            WHERE revenue_allocation_method IN (:legacy_manual_method, :legacy_equal_method)
            """
        ),
        {
            "system_method": "cadence_profile",
            "default_profile": "flat_equal",
            "legacy_manual_method": "manual_monthly_phasing",
            "legacy_equal_method": "equal_monthly_split",
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    allocation_columns = {
        column["name"] for column in inspector.get_columns("monthly_forecast_allocations")
    }
    if "manual_note" in allocation_columns:
        op.drop_column("monthly_forecast_allocations", "manual_note")
