"""add shared forecast phasing draft persistence

Revision ID: 20260401_03_phase_draft
Revises: 20260401_02_rev_phase
Create Date: 2026-04-01 22:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260401_03_phase_draft"
down_revision = "20260401_02_rev_phase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_phasing_drafts",
        sa.Column("forecast_version_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("discipline_id", sa.String(length=32), nullable=True),
        sa.Column("updated_by_id", sa.String(length=32), nullable=True),
        sa.Column("row_mode", sa.String(length=32), nullable=False),
        sa.Column("row_key", sa.String(length=96), nullable=False),
        sa.Column("save_mode", sa.String(length=16), nullable=False, server_default="replace"),
        sa.Column("current_state", sa.JSON(), nullable=False),
        sa.Column("past_states", sa.JSON(), nullable=False),
        sa.Column("future_states", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["discipline_id"],
            ["disciplines.id"],
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
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_phasing_drafts_project_updated_at",
        "forecast_phasing_drafts",
        ["project_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_forecast_phasing_drafts_version_row_key",
        "forecast_phasing_drafts",
        ["forecast_version_id", "row_key"],
        unique=True,
    )
    op.alter_column("forecast_phasing_drafts", "save_mode", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_forecast_phasing_drafts_version_row_key",
        table_name="forecast_phasing_drafts",
    )
    op.drop_index(
        "ix_forecast_phasing_drafts_project_updated_at",
        table_name="forecast_phasing_drafts",
    )
    op.drop_table("forecast_phasing_drafts")
