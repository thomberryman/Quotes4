"""add prediction persistence tables and predictive input fields

Revision ID: 20260331_03_prediction_runs
Revises: 20260331_02_ceta
Create Date: 2026-03-31 21:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models import (
    PredictionEvaluation,
    PredictionModuleOutput,
    PredictionOverride,
    PredictionRun,
    PredictionRunComparable,
    PredictionScenario,
)

# revision identifiers, used by Alembic.
revision = "20260331_03_prediction_runs"
down_revision = "20260331_02_ceta"
branch_labels = None
depends_on = None


TABLES = [
    PredictionRun.__table__,
    PredictionModuleOutput.__table__,
    PredictionRunComparable.__table__,
    PredictionScenario.__table__,
    PredictionOverride.__table__,
    PredictionEvaluation.__table__,
]


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("projects", sa.Column("pipeline_stage_key", sa.String(length=100), nullable=True))
    op.add_column("projects", sa.Column("bid_owner_user_id", sa.String(length=32), nullable=True))
    op.add_column(
        "projects",
        sa.Column("strategic_account_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_projects_bid_owner_user_id_users",
        "projects",
        "users",
        ["bid_owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "project_metadata",
        sa.Column("project_format_key", sa.String(length=100), nullable=True),
    )
    op.add_column("quote_versions", sa.Column("pricing_context", sa.JSON(), nullable=True))
    op.add_column(
        "quote_line_items",
        sa.Column("subcategory_key", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "quote_line_items",
        sa.Column("revenue_category_key", sa.String(length=100), nullable=True),
    )
    PredictionRun.metadata.create_all(bind=bind, tables=TABLES, checkfirst=True)
    op.alter_column("projects", "strategic_account_flag", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    PredictionRun.metadata.drop_all(bind=bind, tables=TABLES, checkfirst=True)
    op.drop_constraint("fk_projects_bid_owner_user_id_users", "projects", type_="foreignkey")
    op.drop_column("quote_line_items", "revenue_category_key")
    op.drop_column("quote_line_items", "subcategory_key")
    op.drop_column("quote_versions", "pricing_context")
    op.drop_column("project_metadata", "project_format_key")
    op.drop_column("projects", "strategic_account_flag")
    op.drop_column("projects", "bid_owner_user_id")
    op.drop_column("projects", "pipeline_stage_key")
