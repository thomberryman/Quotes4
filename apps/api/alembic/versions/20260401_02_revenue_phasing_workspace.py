"""add revenue phasing workspace fields and audit tables

Revision ID: 20260401_02_rev_phase
Revises: 20260401_01_unified_forecast
Create Date: 2026-04-01 18:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260401_02_rev_phase"
down_revision = "20260401_01_unified_forecast"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("estimated_execution_start_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("estimated_execution_end_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column(
            "revenue_allocation_method",
            sa.String(length=48),
            nullable=False,
            server_default="cadence_profile",
        ),
    )
    op.add_column(
        "projects",
        sa.Column("cadence_profile_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("cadence_profile_data", sa.JSON(), nullable=True),
    )
    op.create_check_constraint(
        "project_estimated_execution_dates",
        "projects",
        "estimated_execution_end_date IS NULL "
        "OR estimated_execution_start_date IS NULL "
        "OR estimated_execution_end_date >= estimated_execution_start_date",
    )
    op.create_index(
        "ix_projects_estimated_execution_dates",
        "projects",
        ["estimated_execution_start_date", "estimated_execution_end_date"],
        unique=False,
    )
    op.alter_column("projects", "revenue_allocation_method", server_default=None)

    op.add_column(
        "monthly_forecast_allocations",
        sa.Column("is_manual_override", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "monthly_forecast_allocations",
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("monthly_forecast_allocations", "is_manual_override", server_default=None)
    op.alter_column("monthly_forecast_allocations", "is_locked", server_default=None)

    op.create_table(
        "forecast_phasing_changes",
        sa.Column("forecast_version_id", sa.String(length=32), nullable=False),
        sa.Column("forecast_line_id", sa.String(length=32), nullable=True),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("discipline_id", sa.String(length=32), nullable=True),
        sa.Column("actor_id", sa.String(length=32), nullable=True),
        sa.Column("row_mode", sa.String(length=32), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("before_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("after_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("before_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("after_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_method", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["discipline_id"],
            ["disciplines.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["forecast_line_id"],
            ["forecast_lines.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["forecast_version_id"],
            ["forecast_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_phasing_changes_project_created_at",
        "forecast_phasing_changes",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_forecast_phasing_changes_version_month",
        "forecast_phasing_changes",
        ["forecast_version_id", "month"],
        unique=False,
    )
    op.create_index(
        "ix_forecast_phasing_changes_line_month",
        "forecast_phasing_changes",
        ["forecast_line_id", "month"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_phasing_changes_line_month", table_name="forecast_phasing_changes")
    op.drop_index(
        "ix_forecast_phasing_changes_version_month",
        table_name="forecast_phasing_changes",
    )
    op.drop_index(
        "ix_forecast_phasing_changes_project_created_at",
        table_name="forecast_phasing_changes",
    )
    op.drop_table("forecast_phasing_changes")

    op.drop_column("monthly_forecast_allocations", "is_locked")
    op.drop_column("monthly_forecast_allocations", "is_manual_override")

    op.drop_index("ix_projects_estimated_execution_dates", table_name="projects")
    op.drop_constraint("project_estimated_execution_dates", "projects", type_="check")
    op.drop_column("projects", "cadence_profile_data")
    op.drop_column("projects", "cadence_profile_type")
    op.drop_column("projects", "revenue_allocation_method")
    op.drop_column("projects", "estimated_execution_end_date")
    op.drop_column("projects", "estimated_execution_start_date")
